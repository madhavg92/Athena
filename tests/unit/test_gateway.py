from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from athena.core.config import AthenaConfig
from athena.core.db import Database, DigestItem, Receipt
from athena.core.gateway import Action, Gateway, MemoryDeliverer, Source
from athena.core.killswitch import set_switch

NOW = datetime(2026, 10, 6, 6, 0, tzinfo=UTC)  # 11:30 in Asia/Kolkata, inside 10:00-19:00
DM = "dm.one@fixture.local"
HL = "hl.key@fixture.local"


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock(NOW)


@pytest.fixture
def out() -> MemoryDeliverer:
    return MemoryDeliverer()


@pytest.fixture
def gw(cfg: AthenaConfig, db: Database, out: MemoryDeliverer, clock: Clock) -> Gateway:
    return Gateway(cfg, db, out, clock)


def notify(**kw) -> Action:
    base = dict(
        type="notify",
        rule_id="R2",
        actor="athena",
        recipients=[DM],
        clients=["northwind_ortho"],
        text="Task T-1 for Northwind Orthopedics is late.",
        sources=[Source(name="smartsheet", as_of=NOW - timedelta(minutes=5))],
        item_key="R2:T-1",
        mode="live",
        delivery="now",
    )
    base.update(kw)
    return Action(**base)


def test_pass_all_checks_sends(gw: Gateway, out: MemoryDeliverer, db: Database) -> None:
    result = gw.submit(notify())
    assert result.status == "ok" and result.per_recipient == {DM: "sent"}
    assert out.sent[0][0] == DM
    with db.session() as s:
        receipt = s.scalars(select(Receipt)).one()
    assert receipt.status == "sent" and receipt.item_key == "R2:T-1"


# 1 kill switch
def test_kill_switch_refuses(gw: Gateway, db: Database, out: MemoryDeliverer) -> None:
    set_switch(db, "rule", "R2", True, "ops")
    result = gw.submit(notify())
    assert result.refused and result.reason == "kill switch: rule R2" and not out.sent
    with db.session() as s:
        assert s.scalars(select(Receipt)).one().status == "refused"


def test_user_kill_switch(gw: Gateway, db: Database) -> None:
    set_switch(db, "user", DM, True, "ops")
    assert gw.submit(notify()).reason.startswith("kill switch: user")


# 2 action type
def test_write_refused(gw: Gateway) -> None:
    assert "write is disabled" in gw.submit(notify(type="write")).reason


# 3 recipients internal
def test_external_recipient_refused(gw: Gateway) -> None:
    assert "not internal" in gw.submit(notify(recipients=["x@client-example.com"])).reason


# 4 scope
def test_out_of_scope_recipient_refused(gw: Gateway) -> None:
    assert gw.submit(notify(clients=["cedar_family_clinic"])).reason.startswith("scope:")


def test_answer_checks_actor_scope(gw: Gateway) -> None:
    a = notify(
        type="answer", rule_id="R1", actor=DM, recipients=[DM], clients=["bluefield_imaging"]
    )
    assert gw.submit(a).reason.startswith("scope:")
    assert gw.submit(notify(type="answer", rule_id="R1", actor=DM)).status == "ok"


# 5 freshness
def test_stale_source_refused(gw: Gateway) -> None:
    old = [Source(name="smartsheet", as_of=NOW - timedelta(hours=2))]
    assert gw.submit(notify(sources=old)).reason.startswith("freshness:")


def test_stale_source_allowed_when_text_says_so(gw: Gateway) -> None:
    old = [Source(name="smartsheet", as_of=NOW - timedelta(hours=2))]
    a = notify(sources=old, text="Data is not current (as of 04:00). Task T-1 is late.")
    assert gw.submit(a).status == "ok"


# 6 PHI lint
def test_phi_refused(gw: Gateway) -> None:
    assert gw.submit(notify(text="Patient John Smith DOB 01/02/1960")).reason.startswith("phi lint")


# 7 message limit
def test_message_limit(gw: Gateway) -> None:
    assert gw.submit(notify()).status == "ok"
    assert gw.submit(notify()).status == "ok"
    third = gw.submit(notify())
    assert third.refused and third.reason.startswith("message limit")
    assert gw.submit(notify(recipients=[HL])).status == "ok"  # another person is fine


# 8 work hours
def test_outside_hours_held_then_released(gw: Gateway, clock: Clock, out: MemoryDeliverer) -> None:
    clock.now = datetime(2026, 10, 6, 16, 0, tzinfo=UTC)  # 21:30 IST
    a = notify(sources=[Source(name="smartsheet", as_of=clock.now)])
    assert gw.submit(a).per_recipient == {DM: "held"}
    assert not out.sent
    assert gw.release_held() == 0
    clock.now = datetime(2026, 10, 7, 4, 31, tzinfo=UTC)  # 10:01 IST next day
    assert gw.release_held() == 1
    assert out.sent[0][0] == DM


def test_digest_delivery_queues(gw: Gateway, db: Database, out: MemoryDeliverer) -> None:
    result = gw.submit(notify(delivery="digest"))
    assert result.per_recipient == {DM: "queued"} and not out.sent
    with db.session() as s:
        assert s.scalars(select(DigestItem)).one().user == DM


# 9 mode
def test_shadow_not_delivered(gw: Gateway, out: MemoryDeliverer) -> None:
    assert gw.submit(notify(mode="shadow")).per_recipient == {DM: "shadow"}
    assert not out.sent


def test_checks_run_in_order(gw: Gateway, db: Database) -> None:
    set_switch(db, "global", "", True, "ops")
    a = notify(type="write", recipients=["x@client-example.com"], text="SSN 123-45-6789")
    assert gw.submit(a).reason == "kill switch: global"
