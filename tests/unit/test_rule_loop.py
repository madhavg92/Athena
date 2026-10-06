from datetime import timedelta

import pytest
from sqlalchemy import select

from athena.app import build
from athena.core import ladder, scheduler
from athena.core.db import Alert, Receipt, RuleState

DM1, HL = "dm.one@fixture.local", "hl.key@fixture.local"


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


@pytest.fixture
def clock(anchor):
    return Clock(anchor)


@pytest.fixture
def live_cfg(cfg):
    """R2 in live mode, so messages are delivered (tests only)."""
    rules = dict(cfg.rules)
    rules["R2"] = rules["R2"].model_copy(update={"mode": "live"})
    return cfg.model_copy(update={"rules": rules})


def make(cfg, db, clock):
    return build(cfg=cfg, db=db, clock=clock, run_mode="fixture")


def receipts(app, **where):
    with app.db.session() as s:
        q = select(Receipt)
        for k, v in where.items():
            q = q.where(getattr(Receipt, k) == v)
        return list(s.scalars(q))


def alerts(app, state="open"):
    with app.db.session() as s:
        return list(s.scalars(select(Alert).where(Alert.state == state)))


# ---- M6.2 scheduler


def test_is_due(cfg, anchor) -> None:
    r2, r3 = cfg.rules["R2"], cfg.rules["R3"]
    assert scheduler.is_due(r2, None, anchor)  # */15 always near a fire time
    assert not scheduler.is_due(r3, None, anchor)  # 08:30 IST weekdays; anchor is 11:30 IST
    assert scheduler.is_due(r3, anchor - timedelta(days=1), anchor)  # missed run catches up once
    assert not scheduler.is_due(r2, anchor, anchor)


def test_r2_opens_alerts_for_late_and_at_risk(live_cfg, db, clock) -> None:
    app = make(live_cfg, db, clock)
    run = scheduler.run_rule(app, app.cfg.rules["R2"])
    assert (
        not run.stale and run.hits == run.opened == 12
    )  # 2 late + 2 at risk per client... see fixtures
    sev = {a.severity for a in alerts(app)}
    assert sev == {"late", "at_risk"}
    first = receipts(app, rule_id="R2")
    assert first and all(r.recipient.startswith("dm.") for r in first)  # step 0: DM/AM


def test_alert_closes_when_clear(live_cfg, db, clock) -> None:
    app = make(live_cfg, db, clock)
    scheduler.run_rule(app, app.cfg.rules["R2"])
    clock.now += timedelta(
        days=5
    )  # fixture times shift with the clock -> same hits, nothing closes
    run = scheduler.run_rule(app, app.cfg.rules["R2"])
    assert run.closed == 0
    with app.db.session() as s:  # an item that no longer matches is closed
        s.add(
            Alert(
                rule_id="R2",
                item_key="R2:T-GONE",
                client="northwind_ortho",
                severity="late",
                opened_at=clock.now,
            )
        )
    run = scheduler.run_rule(app, app.cfg.rules["R2"])
    assert run.closed == 1 and any(a.item_key == "R2:T-GONE" for a in alerts(app, "closed"))


def test_stale_source_makes_no_alerts(live_cfg, db, clock) -> None:
    rules = dict(live_cfg.rules)
    rules["R2"] = rules["R2"].model_copy(update={"data_max_age": timedelta(minutes=1)})
    app = make(live_cfg.model_copy(update={"rules": rules}), db, clock)
    run = scheduler.run_rule(app, app.cfg.rules["R2"])
    assert run.stale and run.opened == 0 and not alerts(app)
    with app.db.session() as s:
        assert s.get(RuleState, "R2").stale


def test_tick_runs_due_rules_and_shadow(cfg, db, clock) -> None:
    app = make(cfg, db, clock)
    out = scheduler.tick(app)
    assert [r["rule_id"] for r in out["runs"]] == ["R2", "R6"]
    statuses = {r.status for r in receipts(app, rule_id="R2")}
    assert statuses == {"shadow"}  # R2 ships in shadow mode
    assert scheduler.tick(app)["runs"] == []  # not due again in the same window


# ---- M6.3 ladder (fake clock)


def test_ladder_reminder_escalation_and_limit(live_cfg, db, clock) -> None:
    app = make(live_cfg, db, clock)
    r2 = app.cfg.rules["R2"]
    scheduler.run_rule(app, r2)
    key = alerts(app)[0].item_key
    dm = receipts(app, item_key=key)[0].recipient

    def sent_to(person):
        return [
            r for r in receipts(app, item_key=key, recipient=person) if r.status in ("sent", "held")
        ]

    assert len(sent_to(dm)) == 1
    clock.now += timedelta(hours=1)
    scheduler.run_rule(app, r2)
    assert len(sent_to(dm)) == 1  # renudge_after 2h not reached
    clock.now += timedelta(hours=1, minutes=1)
    scheduler.run_rule(app, r2)
    assert len(sent_to(dm)) == 2 and sent_to(dm)[1].output.startswith("Reminder:")
    clock.now += timedelta(hours=1)
    scheduler.run_rule(app, r2)
    assert len(sent_to(dm)) == 2  # at most 2 per person per step
    clock.now += timedelta(hours=1)  # 4h+ since open -> hub leader
    scheduler.run_rule(app, r2)
    hl = app.cfg.owner_map.clients[alerts(app)[0].client].role("hub_leader")
    assert len(sent_to(hl)) == 1 and len(sent_to(dm)) == 2
    with app.db.session() as s:
        assert s.scalars(select(Alert).where(Alert.item_key == key)).one().ladder_step == 1


def test_current_step(cfg, anchor) -> None:
    r2 = cfg.rules["R2"]
    a = Alert(
        rule_id="R2", item_key="k", client="northwind_ortho", severity="late", opened_at=anchor
    )
    assert ladder.current_step(r2, a, anchor + timedelta(hours=3)) == 0
    assert ladder.current_step(r2, a, anchor + timedelta(hours=4)) == 1
    assert ladder.recipients(cfg, r2, a, 1) == [HL]


def test_tick_cli(monkeypatch, tmp_path) -> None:
    from typer.testing import CliRunner

    from athena.cli import app as cli

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    result = CliRunner().invoke(cli, ["tick", "--rule", "R2"])
    assert result.exit_code == 0, result.output
    assert "R2: 12 hits, 12 opened" in result.output and "shadow" in result.output
