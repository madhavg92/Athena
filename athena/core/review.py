"""Shadow review: owners mark shadow alerts correct or wrong. Also automatic phase demotion (M6.7)."""

from __future__ import annotations

from typing import Literal

from sqlalchemy import select

from athena.app import App
from athena.core.db import Alert, Receipt, ReviewMark

Verdict = Literal["correct", "wrong"]


def pending(app: App, rule_id: str | None = None, include_marked: bool = False) -> list[Alert]:
    """Alerts that went to the review list (shadow receipts), newest first."""
    with app.db.session() as s:
        shadow_keys = set(
            s.scalars(
                select(Receipt.item_key).where(
                    Receipt.status == "shadow", Receipt.action_type == "notify"
                )
            )
        )
        marked = set(s.scalars(select(ReviewMark.alert_id)))
        q = select(Alert).order_by(Alert.opened_at.desc(), Alert.id.desc())
        if rule_id:
            q = q.where(Alert.rule_id == rule_id)
        return [
            a
            for a in s.scalars(q)
            if a.item_key in shadow_keys and (include_marked or a.id not in marked)
        ]


def can_review(app: App, alert: Alert, reviewer: str) -> bool:
    """The owners of the alert's client (any owner-map role) may mark it."""
    client = app.cfg.owner_map.clients.get(alert.client or "")
    return client is not None and reviewer.lower() in {e.lower() for e in client.roles.values()}


def mark(
    app: App, alert_id: int, reviewer: str, verdict: Verdict, note: str | None = None
) -> str | None:
    """Record a verdict. Returns an error message, or None when recorded."""
    if verdict not in ("correct", "wrong"):
        return f"verdict must be correct or wrong, not {verdict!r}"
    with app.db.session() as s:
        alert = s.get(Alert, alert_id)
        if alert is None:
            return f"no alert {alert_id}"
        if not can_review(app, alert, reviewer):
            return f"{reviewer} is not an owner of {alert.client}"
        s.add(
            ReviewMark(
                alert_id=alert_id,
                reviewer=reviewer.lower(),
                verdict=verdict,
                note=note,
                time=app.clock(),
            )
        )
    return None


def apply_demotion(app: App) -> list[str]:
    """Built in M6.7."""
    return []
