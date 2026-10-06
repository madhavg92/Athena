"""Shadow review: owners mark shadow alerts correct or wrong. Also automatic phase demotion (M6.7)."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Literal

from sqlalchemy import select

from athena.app import App
from athena.core.db import Alert, Receipt, ReviewMark, RuleState, as_utc

log = logging.getLogger(__name__)

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


WINDOW = timedelta(days=7)


def wrong_rate(app: App, rule_id: str) -> tuple[int, int]:
    """(wrong, reviewed) marks in the last 7 days for a rule's alerts."""
    since = app.clock() - WINDOW
    with app.db.session() as s:
        rows = s.execute(
            select(ReviewMark.verdict, ReviewMark.time)
            .join(Alert, Alert.id == ReviewMark.alert_id)
            .where(Alert.rule_id == rule_id)
        ).all()
    recent = [v for v, t in rows if as_utc(t) >= since]
    return sum(v == "wrong" for v in recent), len(recent)


def apply_demotion(app: App) -> list[str]:
    """If wrong alerts in the last 7 days exceed max_wrong_rate, set the rule one phase lower and record it.
    At most one demotion per rule per 7 days. Phase 1 cannot go lower; that is recorded too."""
    from athena.core.scheduler import effective_phase, rule_state

    now = app.clock()
    changed = []
    for rule in app.cfg.rules.values():
        if rule.max_wrong_rate is None:
            continue
        wrong, reviewed = wrong_rate(app, rule.id)
        if not reviewed or wrong / reviewed <= rule.max_wrong_rate:
            continue
        state = rule_state(app, rule.id)
        if state.phase_changed_at and now - as_utc(state.phase_changed_at) < WINDOW:
            continue
        phase = effective_phase(app, rule)
        new_phase = max(1, phase - 1)
        reason = f"{wrong}/{reviewed} wrong in 7 days > max_wrong_rate {rule.max_wrong_rate}"
        if new_phase == phase:
            reason += "; already phase 1"
        with app.db.session() as s:
            row = s.get(RuleState, rule.id)
            row.phase, row.phase_reason, row.phase_changed_at = new_phase, reason, now
        log.warning("phase demotion", extra={"rule": rule.id, "from": phase, "to": new_phase})
        changed.append(f"{rule.id}: phase {phase} -> {new_phase} ({reason})")
    return changed
