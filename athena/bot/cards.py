"""Adaptive Cards (schema 1.5) for Teams."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from athena.core.ask import AskResult

SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"


def _card(body: list[dict], actions: list[dict] | None = None) -> dict[str, Any]:
    card: dict[str, Any] = {
        "$schema": SCHEMA,
        "type": "AdaptiveCard",
        "version": "1.5",
        "body": body,
    }
    if actions:
        card["actions"] = actions
    return card


def answer_card(result: AskResult, tz: str = "Asia/Kolkata") -> dict[str, Any]:
    body: list[dict] = []
    if result.stale:
        body.append(
            {
                "type": "TextBlock",
                "text": "Data is not current",
                "color": "Warning",
                "weight": "Bolder",
                "wrap": True,
            }
        )
    body.append({"type": "TextBlock", "text": result.answer, "wrap": True})
    if result.sources:
        items = []
        for s in result.sources:
            name = f"[{s.name}]({s.ref})" if s.ref and s.ref.startswith("https://") else s.name
            items.append(
                {
                    "type": "TextBlock",
                    "text": f"{name} · as of {s.as_of.astimezone(ZoneInfo(tz)):%Y-%m-%d %H:%M}",
                    "size": "Small",
                    "isSubtle": True,
                    "wrap": True,
                    "spacing": "None",
                }
            )
        body.append(
            {
                "type": "Container",
                "separator": True,
                "items": [
                    {"type": "TextBlock", "text": "Sources", "size": "Small", "weight": "Bolder"},
                    *items,
                ],
            }
        )
    return _card(body)


def alert_card(alert_id: int, text: str, severity: str, shadow: bool = False) -> dict[str, Any]:
    """An alert. Live alerts have actions (I'm on it, Snooze, Not useful, Ask about this).
    In shadow review, Correct and Wrong buttons write review marks."""
    body = [
        {
            "type": "TextBlock",
            "text": severity.replace("_", " ").capitalize(),
            "weight": "Bolder",
            "color": "Attention" if severity == "late" else "Warning",
        },
        {"type": "TextBlock", "text": text, "wrap": True},
    ]
    if shadow:
        actions = [
            {
                "type": "Action.Submit",
                "title": "Correct",
                "data": {"athena": "review", "alert_id": alert_id, "verdict": "correct"},
            },
            {
                "type": "Action.Submit",
                "title": "Wrong",
                "data": {"athena": "review", "alert_id": alert_id, "verdict": "wrong"},
            },
        ]
        return _card(body, actions)
    actions = [
        {
            "type": "Action.Submit",
            "title": "I'm on it",
            "data": {"athena": "ack", "alert_id": alert_id},
        },
        {
            "type": "Action.Submit",
            "title": "Snooze 4h",
            "data": {"athena": "snooze", "alert_id": alert_id, "hours": 4},
        },
        {
            "type": "Action.ShowCard",
            "title": "Ask about this",
            "card": {
                "type": "AdaptiveCard",
                "version": "1.5",
                "body": [
                    {
                        "type": "Input.Text",
                        "id": "question",
                        "placeholder": "Why is this late? What should I do?",
                        "isMultiline": True,
                    }
                ],
                "actions": [
                    {
                        "type": "Action.Submit",
                        "title": "Ask",
                        "data": {"athena": "alert_ask", "alert_id": alert_id},
                    },
                    {
                        "type": "Action.Submit",
                        "title": "Draft a note to the owner",
                        "data": {"athena": "alert_draft", "alert_id": alert_id},
                    },
                ],
            },
        },
        {
            "type": "Action.Submit",
            "title": "Not useful",
            "data": {"athena": "review", "alert_id": alert_id, "verdict": "wrong"},
        },
    ]
    return _card(body, actions)
