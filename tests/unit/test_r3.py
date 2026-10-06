"""M7.2: R3 in fixture mode, delivery routing now vs digest."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from athena.app import build
from athena.core import scheduler
from athena.core.db import DigestItem

# Monday 2026-10-05: 08:30 IST = 03:00 UTC (R3 runs), 09:00 IST = 03:30 UTC (hub leader digest)
R3_TIME = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)
HL = "hl.key@fixture.local"


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def make(cfg, db, now, live=False):
    if live:
        rules = {k: v.model_copy(update={"mode": "live"}) for k, v in cfg.rules.items()}
        cfg = cfg.model_copy(update={"rules": rules})
    clock = Clock(now)
    return build(cfg=cfg, db=db, clock=clock, run_mode="fixture"), clock


def test_r3_routes_to_digest_then_one_message(cfg, db) -> None:
    app, clock = make(cfg, db, R3_TIME, live=True)
    out = scheduler.tick(app)
    assert [r["rule_id"] for r in out["runs"]] == ["R2", "R3", "R6"]
    with app.db.session() as s:
        items = list(s.scalars(select(DigestItem).where(DigestItem.user == HL)))
    assert items and all(i.sent_at is None for i in items)  # routed to digest, not sent now
    assert not [m for m in app.gateway.deliverer.sent if m[0] == HL and "R3" == m[2].rule_id]
    clock.now = R3_TIME + timedelta(minutes=30)
    scheduler.tick(app)
    msgs = [m for m in app.gateway.deliverer.sent if m[0] == HL and m[2].rule_id == "R3"]
    assert len(msgs) == 1
    text = msgs[0][1]
    assert (
        text.startswith("Daily exception digest: Mon 05 Oct")
        and "Open alerts:" in text
        and "R2 late" in text
    )
    assert "Cedar" not in text  # not in hl.key's scope
    clock.now += timedelta(hours=2)
    scheduler.tick(app)
    assert (
        len([m for m in app.gateway.deliverer.sent if m[0] == HL and m[2].rule_id == "R3"]) == 1
    )  # once a day


def test_now_rules_bypass_digest(cfg, db) -> None:
    app, _ = make(
        cfg, db, R3_TIME + timedelta(hours=2), live=True
    )  # 10:30 IST, inside DM work hours
    scheduler.run_rule(app, app.cfg.rules["R2"])
    to_dm = [
        m for m in app.gateway.deliverer.sent if m[0].startswith("dm.") and m[2].rule_id == "R2"
    ]
    assert to_dm  # delivery: now -> sent at once
    with app.db.session() as s:
        assert not list(s.scalars(select(DigestItem).where(DigestItem.rule_id == "R2")))
