"""Two-way alerts: the person who gets an alert can act on it in Athena.

All actions change Athena's own records only. Nothing is written to Smartsheet, CS Hub or any
other source system (writes stay disabled in releases 1 and 2). Each action goes through the
gateway and writes a receipt.
"""

from __future__ import annotations

import json
from datetime import timedelta

from athena.app import App
from athena.core import review
from athena.core.ask import AskResult
from athena.core.db import Alert

ACK_HOURS = 2
SNOOZE_HOURS = 4


class ActionResult:
    def __init__(self, ok: bool, message: str, answer: AskResult | None = None) -> None:
        self.ok, self.message, self.answer = ok, message, answer


def _alert(app: App, alert_id: int) -> Alert | None:
    with app.db.session() as s:
        return s.get(Alert, alert_id)


def describe(app: App, alert: Alert) -> str:
    """The alert as plain facts, for the model (payload is already scrubbed by the connectors)."""
    p = {k: v for k, v in (alert.payload or {}).items() if not k.startswith("_")}
    client = app.cfg.owner_map.clients.get(alert.client or "")
    return json.dumps(
        {
            "alert_id": alert.id,
            "rule": f"{alert.rule_id} {app.cfg.rules[alert.rule_id].name}"
            if alert.rule_id in app.cfg.rules
            else alert.rule_id,
            "severity": alert.severity,
            "client": client.name if client else alert.client,
            "item": alert.item_key.split(":", 1)[-1],
            "opened_at_utc": alert.opened_at.isoformat() if alert.opened_at else None,
            "state": alert.state,
            "fields": p,
        },
        default=str,
    )


def _set_pause(app: App, alert_id: int, key: str, user: str, hours: float) -> None:
    until = app.clock() + timedelta(hours=hours)
    with app.db.session() as s:
        row = s.get(Alert, alert_id)
        row.payload = {**(row.payload or {}), key: until.isoformat(), f"{key}_by": user.lower()}


def _guarded(
    app: App, alert_id: int, user: str, kind: str, text: str
) -> tuple[Alert | None, str | None]:
    alert = _alert(app, alert_id)
    if alert is None:
        return None, f"No alert {alert_id}."
    if alert.state != "open":
        return None, f"Alert {alert_id} is already closed."
    result = app.gateway.record(
        kind,
        user.lower(),
        alert.rule_id,
        [alert.client] if alert.client else [],
        alert.item_key,
        text,
    )
    if result.refused:
        return None, "You are not an owner of this client." if (result.reason or "").startswith(
            "scope"
        ) else f"Not allowed: {result.reason}"
    return alert, None


def acknowledge(app: App, alert_id: int, user: str, hours: float = ACK_HOURS) -> ActionResult:
    alert, error = _guarded(app, alert_id, user, "acknowledge", f"Acknowledged for {hours:g}h")
    if error:
        return ActionResult(False, error)
    _set_pause(app, alert.id, "_ack_until", user, hours)
    return ActionResult(
        True,
        f"Got it. No reminders or escalation for {hours:g} hours. If it is still open after that, the ladder carries on.",
    )


def snooze(app: App, alert_id: int, user: str, hours: float = SNOOZE_HOURS) -> ActionResult:
    alert, error = _guarded(app, alert_id, user, "snooze", f"Snoozed for {hours:g}h")
    if error:
        return ActionResult(False, error)
    _set_pause(app, alert.id, "_snoozed_until", user, hours)
    return ActionResult(True, f"Snoozed for {hours:g} hours.")


def not_useful(app: App, alert_id: int, user: str, note: str | None = None) -> ActionResult:
    error = review.mark(app, alert_id, user, "wrong", note)
    if error:
        return ActionResult(False, error)
    return ActionResult(
        True, "Thanks. Marked as not useful; this counts towards the rule's wrong-alert rate."
    )


def ask_about(
    app: App, alert_id: int, user: str, question: str, conversation_id: str | None = None
) -> ActionResult:
    alert = _alert(app, alert_id)
    if alert is None:
        return ActionResult(False, f"No alert {alert_id}.")
    if app.gateway.owner_problem(user, [alert.client] if alert.client else []):
        return ActionResult(False, "You are not an owner of this client.")
    result = app.asker.ask(
        question,
        user,
        conversation_id=conversation_id or f"alert-{alert_id}-{user.lower()}",
        context=describe(app, alert),
    )
    return ActionResult(not result.refused, result.answer, result)


def draft_note(app: App, alert_id: int, user: str, to: str = "the task owner") -> ActionResult:
    """A draft only: it is shown to the user, never sent."""
    question = (
        f"Draft a short, polite note from me to {to} about this alert: what is wrong, why (use the tools to find out), "
        "and what I need by when. Plain text, under 120 words. Do not invent dates or names."
    )
    r = ask_about(app, alert_id, user, question, conversation_id=f"draft-{alert_id}-{user.lower()}")
    if r.answer is not None:
        r.message = "DRAFT (review before sending; Athena does not send it):\n" + r.answer.answer
    return r
