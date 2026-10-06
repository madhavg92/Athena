import json

from athena.bot.cards import alert_card, answer_card
from athena.bot.teams import TeamsBot

DM_ID = "00000000-0000-4000-8000-000000000003"


def test_answer_card(app) -> None:
    result = app.asker.ask("Which tasks are late for Northwind?", "dm.one@fixture.local")
    card = answer_card(result)
    assert card["type"] == "AdaptiveCard" and card["version"] == "1.5"
    assert card["body"][0]["text"] == result.answer
    sources = card["body"][1]
    assert sources["items"][0]["text"] == "Sources"
    assert "[smartsheet.tasks](https://app.smartsheet.com/sheets/" in sources["items"][1]["text"]
    json.dumps(card)


def test_stale_card_has_warning(app) -> None:
    result = app.asker.ask(
        "What is the health score for Cedar Family Clinic?", "hl.small@fixture.local"
    )
    assert answer_card(result)["body"][0]["text"] == "Data is not current"


def test_bot_reply_has_card(app) -> None:
    reply = TeamsBot(app).handle_message("Who owns Northwind Orthopedics?", DM_ID, None, "c1")
    assert reply.card and reply.card["body"][0]["text"].startswith("Owners for Northwind")


def test_alert_card_review_buttons() -> None:
    card = alert_card(7, "Task T-1 is late.", "late", shadow=True)
    assert [a["data"]["verdict"] for a in card["actions"]] == ["correct", "wrong"]
    assert "actions" not in alert_card(7, "x", "late")
