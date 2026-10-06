from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from athena.app import build
from athena.core import digest, scheduler
from athena.core.db import Receipt

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


def receipts(app, key_prefix):
    with app.db.session() as s:
        return [r for r in s.scalars(select(Receipt)) if (r.item_key or "").startswith(key_prefix)]


def test_empty_digest(cfg, db) -> None:
    app, clock = make(cfg, db, R3_TIME + timedelta(minutes=30))
    scheduler._set_state(app, "R3", stale=False, last_run_at=R3_TIME)
    rule = app.cfg.rules["R3"].model_copy(update={"include_standing": False})
    text, _, _, stale, _ = digest.build_text(app, HL, rule, clock.now)
    assert not stale and text.endswith("No exceptions today.")


def test_digest_starts_with_standing_items_that_need_you(cfg, db) -> None:
    app, clock = make(cfg, db, R3_TIME + timedelta(minutes=30))
    scheduler._set_state(app, "R3", stale=False, last_run_at=R3_TIME)
    text, _, _, _, _ = digest.build_text(app, HL, app.cfg.rules["R3"], clock.now)
    lines = text.splitlines()
    assert lines[1] == "Needs you today:" and lines[2].startswith("- Not working today:")
    assert "No exceptions today" not in text and "Promises made" not in text  # only what needs you


def test_stale_digest_never_all_clear(cfg, db) -> None:
    app, clock = make(cfg, db, R3_TIME + timedelta(minutes=30))
    text, _, _, stale, _ = digest.build_text(
        app, HL, app.cfg.rules["R3"], clock.now
    )  # R3 never ran
    assert stale and "Data is not current" in text
    assert "No exceptions today" not in text and "All on target" not in text
    assert (
        digest.send_due_digests(app) >= 1
    )  # gateway allows it: the text says the data is not current


def test_not_on_weekend_or_before_time(cfg, db) -> None:
    app, _ = make(cfg, db, R3_TIME)
    rule = app.cfg.rules["R3"]
    assert not digest.is_due(app, HL, rule, R3_TIME)  # 08:30 < 09:00
    saturday = R3_TIME + timedelta(days=5, minutes=30)
    assert not digest.is_due(app, HL, rule, saturday)
    assert (
        digest.digest_rules(app, "dm.one@fixture.local") == []
    )  # dm_am persona has no digest rule


def test_shadow_digest_goes_to_review_list(cfg, db) -> None:
    app, clock = make(cfg, db, R3_TIME)
    scheduler.tick(app)
    clock.now += timedelta(minutes=30)
    scheduler.tick(app)
    assert not [m for m in app.gateway.deliverer.sent if m[2].rule_id == "R3"]
    assert {r.status for r in receipts(app, "digest:R3:")} == {"shadow"}
