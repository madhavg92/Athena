from datetime import timedelta

from sqlalchemy import select

from athena.app import build
from athena.bot.cards import alert_card
from athena.bot.teams import TeamsBot
from athena.core import alert_actions as aa
from athena.core import scheduler
from athena.core.db import Alert, Receipt
from athena.core.killswitch import set_switch

DM = "dm.one@fixture.local"
DM_ID = "00000000-0000-4000-8000-000000000003"


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def live_app(cfg, db, anchor):
    rules = dict(cfg.rules)
    rules["R2"] = rules["R2"].model_copy(update={"mode": "live"})
    clock = Clock(anchor)
    app = build(cfg=cfg.model_copy(update={"rules": rules}), db=db, clock=clock, run_mode="fixture")
    scheduler.run_rule(app, app.cfg.rules["R2"])
    return app, clock


def northwind_alert(app):
    with app.db.session() as s:
        return s.scalars(
            select(Alert).where(Alert.client == "northwind_ortho", Alert.severity == "late")
        ).first()


def sent_to(app, key, person):
    return [m for m in app.gateway.deliverer.sent if m[0] == person and m[2].item_key == key]


def test_ack_pauses_reminder_and_escalation(cfg, db, anchor) -> None:
    app, clock = live_app(cfg, db, anchor)
    a = northwind_alert(app)
    assert aa.acknowledge(app, a.id, DM, hours=5).ok
    clock.now += timedelta(
        hours=4, minutes=30
    )  # reminder (2h) and escalation (4h) both due, but paused
    scheduler.run_rule(app, app.cfg.rules["R2"])
    assert len(sent_to(app, a.item_key, DM)) == 1 and not sent_to(
        app, a.item_key, "hl.key@fixture.local"
    )
    clock.now += timedelta(hours=1)  # pause over -> ladder carries on
    scheduler.run_rule(app, app.cfg.rules["R2"])
    assert sent_to(app, a.item_key, "hl.key@fixture.local")
    with app.db.session() as s:
        assert (
            s.scalars(select(Receipt).where(Receipt.action_type == "acknowledge")).one().status
            == "done"
        )


def test_snooze_and_not_useful(cfg, db, anchor) -> None:
    app, _ = live_app(cfg, db, anchor)
    a = northwind_alert(app)
    assert "Snoozed for 4 hours" in aa.snooze(app, a.id, DM).message
    assert aa.not_useful(app, a.id, DM, "extension agreed").ok


def test_only_owners_and_kill_switch(cfg, db, anchor) -> None:
    app, _ = live_app(cfg, db, anchor)
    a = northwind_alert(app)
    assert not aa.acknowledge(app, a.id, "dm.two@fixture.local").ok
    assert not aa.ask_about(app, a.id, "dm.two@fixture.local", "why?").ok
    set_switch(app.db, "user", DM, True, "ops")
    assert "kill switch" in aa.snooze(app, a.id, DM).message
    assert "No alert" in aa.acknowledge(app, 99999, DM).message


def test_ask_about_alert_uses_context(cfg, db, anchor) -> None:
    app, _ = live_app(cfg, db, anchor)
    a = northwind_alert(app)
    seen = []
    real = app.model.chat

    def spy(messages, tools):
        seen.append(messages[0]["content"])
        return real(messages, tools)

    app.model.chat = spy
    r = aa.ask_about(app, a.id, DM, "Which tasks are late for Northwind?")
    assert r.ok and r.answer.tools_used == ["get_tasks"]
    assert "The user is asking about this item" in seen[0] and a.item_key.split(":")[1] in seen[0]
    d = aa.draft_note(app, a.id, DM)
    assert d.message.startswith("DRAFT")


def test_teams_card_and_buttons(cfg, db, anchor) -> None:
    app, _ = live_app(cfg, db, anchor)
    a = northwind_alert(app)
    titles = [x["title"] for x in alert_card(a.id, "t", "late")["actions"]]
    assert titles == ["I'm on it", "Snooze 4h", "Ask about this", "Not useful"]
    bot = TeamsBot(app)
    assert bot.handle_card_action({"athena": "ack", "alert_id": a.id}, DM_ID, None).text.startswith(
        "Got it"
    )
    r = bot.handle_card_action(
        {
            "athena": "alert_ask",
            "alert_id": a.id,
            "question": "Which tasks are late for Northwind?",
        },
        DM_ID,
        None,
    )
    assert r.result is not None and r.card is not None
