from datetime import timedelta

from athena.app import build
from athena.core import review, scheduler


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def setup_app(cfg, db, anchor, phase=2):
    rules = dict(cfg.rules)
    rules["R2"] = rules["R2"].model_copy(update={"phase": phase})
    clock = Clock(anchor)
    app = build(cfg=cfg.model_copy(update={"rules": rules}), db=db, clock=clock, run_mode="fixture")
    scheduler.run_rule(app, app.cfg.rules["R2"])
    return app, clock, review.pending(app)


def mark_n(app, alerts, wrong, right):
    for a in alerts[:wrong]:
        assert (
            review.mark(app, a.id, app.cfg.owner_map.clients[a.client].role("hub_leader"), "wrong")
            is None
        )
    for a in alerts[wrong : wrong + right]:
        assert (
            review.mark(
                app, a.id, app.cfg.owner_map.clients[a.client].role("hub_leader"), "correct"
            )
            is None
        )


def test_demotes_when_wrong_rate_exceeded(cfg, db, anchor) -> None:
    app, clock, alerts = setup_app(cfg, db, anchor)
    mark_n(app, alerts, wrong=3, right=7)  # 30% > 20%
    changed = review.apply_demotion(app)
    assert changed and "phase 2 -> 1" in changed[0]
    assert scheduler.effective_phase(app, app.cfg.rules["R2"]) == 1
    assert review.apply_demotion(app) == []  # once per 7 days


def test_no_demotion_at_or_below_rate(cfg, db, anchor) -> None:
    app, _, alerts = setup_app(cfg, db, anchor)
    mark_n(app, alerts, wrong=2, right=8)  # 20% is not above 20%
    assert review.apply_demotion(app) == []
    assert scheduler.effective_phase(app, app.cfg.rules["R2"]) == 2


def test_old_marks_ignored_and_phase_1_recorded(cfg, db, anchor) -> None:
    app, clock, alerts = setup_app(cfg, db, anchor, phase=1)
    mark_n(app, alerts, wrong=5, right=0)
    clock.now += timedelta(days=8)
    assert review.apply_demotion(app) == []  # marks older than 7 days
    clock.now -= timedelta(days=8)
    changed = review.apply_demotion(app)
    assert "already phase 1" in changed[0]
