"""Teams bot logic, independent of the SDK: who is asking, and what to reply."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from athena.app import App
from athena.bot.cards import answer_card
from athena.connectors.base import NotConfigured
from athena.core.ask import NOT_SET_UP, AskResult

log = logging.getLogger(__name__)


@dataclass
class Reply:
    text: str
    result: AskResult | None = None
    card: dict[str, Any] | None = field(default=None)


def resolve_email(app: App, aad_object_id: str | None, upn: str | None) -> str | None:
    """Map a Teams user to an owner-map email: UPN first, then the Entra object ID."""
    if upn and app.cfg.person(upn):
        return upn.lower()
    if not aad_object_id:
        return None
    try:
        users = app.sources.read("entra.users", id=aad_object_id)
    except NotConfigured:
        log.warning("entra not configured; cannot map teams user")
        return None
    for user in users:
        email = (user.get("email") or "").lower()
        if app.cfg.person(email):
            return email
    return None


class TeamsBot:
    def __init__(self, app: App) -> None:
        self.app = app

    def handle_message(
        self,
        text: str,
        aad_object_id: str | None,
        upn: str | None,
        conversation_id: str,
        user_assertion: str | None = None,
    ) -> Reply:
        email = resolve_email(self.app, aad_object_id, upn)
        if email is None:
            return Reply(text=NOT_SET_UP)
        question = (text or "").strip()
        if not question:
            return Reply(
                text="Ask me about your clients, for example: What is the backlog for <client>?"
            )
        result = self.app.asker.ask(
            question, email, conversation_id=conversation_id, user_assertion=user_assertion
        )
        card = answer_card(result, self.app.cfg.work_hours_of(email)[1])
        return Reply(text=result.text, result=result, card=card)

    def handle_card_action(self, data: dict, aad_object_id: str | None, upn: str | None) -> Reply:
        """Buttons on alert cards: review (Correct / Wrong / Not useful), ack, snooze, ask, draft."""
        from athena.core import alert_actions, review

        email = resolve_email(self.app, aad_object_id, upn)
        if email is None:
            return Reply(text=NOT_SET_UP)
        kind = data.get("athena")
        try:
            alert_id = int(data.get("alert_id"))
        except (TypeError, ValueError):
            return Reply(text="Unknown alert.")
        if kind == "review":
            error = review.mark(
                self.app, alert_id, email, data.get("verdict", ""), data.get("note")
            )
            return Reply(
                text=f"Not recorded: {error}"
                if error
                else f"Thanks. Alert {alert_id} marked {data.get('verdict')}."
            )
        if kind == "ack":
            return Reply(text=alert_actions.acknowledge(self.app, alert_id, email).message)
        if kind == "snooze":
            return Reply(
                text=alert_actions.snooze(
                    self.app, alert_id, email, float(data.get("hours") or 4)
                ).message
            )
        if kind in ("alert_ask", "alert_draft"):
            if kind == "alert_draft":
                r = alert_actions.draft_note(self.app, alert_id, email)
            else:
                question = (
                    str(data.get("question") or "").strip()
                    or "Why is this happening, and what should I do?"
                )
                r = alert_actions.ask_about(self.app, alert_id, email, question)
            card = (
                answer_card(r.answer, self.app.cfg.work_hours_of(email)[1])
                if r.answer and kind == "alert_ask"
                else None
            )
            return Reply(text=r.message, result=r.answer, card=card)
        return Reply(text="Unknown action.")
