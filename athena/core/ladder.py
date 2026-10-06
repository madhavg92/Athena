"""The ladder: who gets each open alert, and when.

Each step has `after` (time since the alert opened) and `to` (an owner-map role). Within a step the
person gets at most 2 messages: the first, then one reminder after `renudge_after`. The gateway also
enforces the limit of 2 notify messages for each item and person.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from athena.core.config import AthenaConfig, Rule
from athena.core.db import Alert, as_utc

MAX_PER_STEP = 2


def paused_until(alert: Alert, now: datetime) -> datetime | None:
    """An acknowledged or snoozed alert sends nothing (no reminder, no escalation) until this time."""
    payload = alert.payload or {}
    times = [
        datetime.fromisoformat(v) for k in ("_ack_until", "_snoozed_until") if (v := payload.get(k))
    ]
    until = max(times, default=None)
    return until if until and until > now else None


def current_step(rule: Rule, alert: Alert, now: datetime) -> int:
    age = now - as_utc(alert.opened_at)
    step = 0
    for i, s in enumerate(rule.ladder):
        if age >= s.after:
            step = i
    return step


def recipients(cfg: AthenaConfig, rule: Rule, alert: Alert, step: int) -> list[str]:
    client = cfg.owner_map.clients.get(alert.client or "")
    if client is None or not rule.ladder:
        return []
    email = client.role(rule.ladder[step].to)
    return [email.lower()] if email else []


def due_sends(
    cfg: AthenaConfig, rule: Rule, alert: Alert, now: datetime
) -> tuple[int, list[tuple[str, str]]]:
    """Return (step, [(person, kind)]) where kind is 'first' or 'reminder'. Digest rules send each run."""
    step = current_step(rule, alert, now)
    if paused_until(alert, now):
        return step, []
    out: list[tuple[str, str]] = []
    counts: dict[str, Any] = alert.sends_count or {}
    last: dict[str, Any] = alert.last_sent_at or {}
    for person in recipients(cfg, rule, alert, step):
        if rule.delivery == "digest":
            out.append((person, "digest"))
            continue
        n = int(counts.get(person, 0))
        if n == 0:
            out.append((person, "first"))
        elif n < MAX_PER_STEP and rule.renudge_after is not None:
            sent = datetime.fromisoformat(last[person]) if person in last else None
            if sent is not None and now - sent >= rule.renudge_after:
                out.append((person, "reminder"))
    return step, out
