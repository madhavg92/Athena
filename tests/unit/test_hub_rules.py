"""R7-R10: hub-ops rules added with YAML and templates only, run on the synthetic fixtures."""

from datetime import timedelta

from sqlalchemy import select

from athena.app import build
from athena.core import scheduler
from athena.core.db import Alert


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def run(cfg, db, anchor, rule_id):
    rules = {k: v.model_copy(update={"mode": "live"}) for k, v in cfg.rules.items()}
    app = build(
        cfg=cfg.model_copy(update={"rules": rules}), db=db, clock=Clock(anchor), run_mode="fixture"
    )
    scheduler.run_rule(app, app.cfg.rules[rule_id])
    with app.db.session() as s:
        alerts = {
            a.item_key.split(":", 1)[1]: a.severity
            for a in s.scalars(select(Alert).where(Alert.rule_id == rule_id))
        }
    return app, alerts


def test_r7_locked_out_and_expiring(cfg, db, anchor) -> None:
    app, alerts = run(cfg, db, anchor, "R7")
    assert alerts == {"BL-301": "locked_out", "BL-302": "expiring"}
    sent = app.gateway.deliverer.sent
    assert {m[0] for m in sent} == {"dm.one@fixture.local", "dm.two@fixture.local"}
    assert any(m[1].startswith("Locked out: 2 people cannot work at Northwind") for m in sent)


def test_r8_waiting_on_client_too_long(cfg, db, anchor) -> None:
    _, alerts = run(cfg, db, anchor, "R8")
    assert set(alerts) == {"BL-303", "BL-304", "BL-306", "BL-310"}  # Cedar too: its DM/AM


def test_r9_unplanned_absence_to_hub_leader(cfg, db, anchor) -> None:
    app, alerts = run(cfg, db, anchor, "R9")
    assert alerts == {"Analyst B2": "unplanned_absence"}
    assert [m[0] for m in app.gateway.deliverer.sent] == ["hl.key@fixture.local"]
    assert "Analyst B2 (Prior auth, Bluefield Imaging)" in app.gateway.deliverer.sent[0][1]


def test_r10_audit_overdue(cfg, db, anchor) -> None:
    _, alerts = run(cfg, db, anchor + timedelta(hours=1), "R10")
    assert alerts == {"QF-41": "client_found_overdue"}
