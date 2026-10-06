"""M9.1 platform test: R6 was added with YAML only (rule, persona, owner-map role)."""

from datetime import timedelta

from athena.app import build
from athena.core import scheduler


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_r6_csm_then_cs_lead(cfg, db, anchor) -> None:
    rules = dict(cfg.rules)
    rules["R6"] = rules["R6"].model_copy(update={"mode": "live"})
    clock = Clock(anchor + timedelta(hours=13))  # 18:30 IST: inside CSM / CS lead hours
    app = build(cfg=cfg.model_copy(update={"rules": rules}), db=db, clock=clock, run_mode="fixture")
    run = scheduler.run_rule(app, app.cfg.rules["R6"])
    assert run.hits > 0 and set(run.messages) == {"sent"}
    first = {m[0] for m in app.gateway.deliverer.sent}
    assert first <= {"csm.one@fixture.local", "csm.two@fixture.local"}
    assert all("ticket CS-" in m[1] for m in app.gateway.deliverer.sent)
    clock.now += timedelta(hours=8)  # 02:30 IST: end of shift -> held; then escalated
    scheduler.run_rule(app, app.cfg.rules["R6"])
    clock.now += timedelta(hours=15)  # next shift
    app.gateway.release_held()
    assert "cs.lead@fixture.local" in {m[0] for m in app.gateway.deliverer.sent}
