"""Digests: one message per person per work day at their digest time.

Items come from rules with `delivery: digest` (queued by the gateway) plus open alerts of the rules in
`include_open_alerts`. Empty -> the rule's `empty_message`. Stale -> "Data is not current", never "All on target".
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from athena.app import App
from athena.core.config import Rule, parse_hhmm
from athena.core.db import Alert, DigestItem, Receipt, as_utc
from athena.core.gateway import STALE_MARK, Action, Source

log = logging.getLogger(__name__)
WORK_DAYS = {0, 1, 2, 3, 4}  # Monday-Friday (provisional, G8)


def digest_rules(app: App, email: str) -> list[Rule]:
    persona = app.cfg.persona_of(email)
    if persona is None:
        return []
    rules = [app.cfg.rules[r] for r in persona.rules if r in app.cfg.rules]
    return [
        r for r in rules if r.action == "notify" and r.delivery == "digest" and not r.is_question
    ]


def digest_key(rule_id: str, email: str, day: str) -> str:
    return f"digest:{rule_id}:{email}:{day}"


def _local(app: App, email: str, now: datetime) -> datetime:
    return now.astimezone(ZoneInfo(app.cfg.work_hours_of(email)[1]))


def is_due(app: App, email: str, rule: Rule, now: datetime) -> bool:
    persona = app.cfg.persona_of(email)
    local = _local(app, email, now)
    if (
        persona is None
        or local.weekday() not in WORK_DAYS
        or local.time() < parse_hhmm(persona.digest_time)
    ):
        return False
    key = digest_key(rule.id, email, local.date().isoformat())
    with app.db.session() as s:
        done = s.scalars(
            select(Receipt.id).where(Receipt.item_key == key, Receipt.status != "refused")
        ).first()
    return done is None


def build_text(
    app: App, email: str, rule: Rule, now: datetime
) -> tuple[str, list[str], list[int], bool, datetime | None]:
    """Returns (text, clients, digest item ids, stale, as_of)."""
    from athena.core.scheduler import rule_state

    scope = set(app.cfg.scope_of(email))
    state = rule_state(app, rule.id)
    last_run = as_utc(state.last_run_at)
    stale = bool(state.stale) or last_run is None or now - last_run > rule.data_max_age
    with app.db.session() as s:
        items = list(
            s.scalars(
                select(DigestItem)
                .where(
                    DigestItem.user == email,
                    DigestItem.rule_id == rule.id,
                    DigestItem.sent_at.is_(None),
                )
                .order_by(DigestItem.id)
            )
        )
        extra = list(
            s.scalars(
                select(Alert)
                .where(Alert.rule_id.in_(rule.include_open_alerts), Alert.state == "open")
                .order_by(Alert.rule_id, Alert.severity, Alert.id)
            )
        )
    extra = [a for a in extra if a.client in scope]
    local = _local(app, email, now)
    lines = [f"{rule.name}: {local:%a %d %b}"]
    if stale:
        when = f"{last_run:%Y-%m-%d %H:%M} UTC" if last_run else "never"
        lines.append(
            f"{STALE_MARK}: {rule.source} was last checked {when}. Exceptions could not be checked."
        )
    needs: list[str] = []
    if rule.include_standing:
        needs = standing_lines(app, email, now)
        lines += needs
    lines += [f"- {i.text}" for i in items]
    if extra:
        lines.append("Open alerts:")
        for a in extra:
            name = app.cfg.owner_map.clients[a.client].name
            title = (
                (a.payload or {}).get("title")
                or (a.payload or {}).get("subject")
                or a.item_key.split(":", 1)[-1]
            )
            lines.append(f"- {a.rule_id} {a.severity.replace('_', ' ')}: {title} ({name})")
    if not items and not extra and not stale and not any(n.startswith("- ") for n in needs):
        lines.append(rule.empty_message or "No exceptions today.")
    clients = sorted(
        {a.client for a in extra}
        | {c for c in scope if any(app.cfg.owner_map.clients[c].name in i.text for i in items)}
    )
    return "\n".join(lines), clients, [i.id for i in items], stale, last_run


def standing_lines(app: App, email: str, now: datetime) -> list[str]:
    """The standing-list items that need this person today (code decides; see core/standing.py)."""
    from athena.connectors.base import NotConfigured
    from athena.core import standing

    try:
        items = standing.standing_list(app.cfg, app.sources, email, now)
    except NotConfigured as exc:
        return [f"Standing list not available: {exc}"]
    needs = [i for i in items if i.needs_you]
    if not needs:
        return ["Nothing on your standing list needs you today."]
    return ["Needs you today:"] + [f"- {i.label}: {i.detail}" for i in needs]


def send_due_digests(app: App) -> int:
    now = app.clock()
    sent = 0
    for email in app.cfg.owner_map.people:
        for rule in digest_rules(app, email):
            if not is_due(app, email, rule, now):
                continue
            text, clients, item_ids, stale, as_of = build_text(app, email, rule, now)
            day = _local(app, email, now).date().isoformat()
            result = app.gateway.submit(
                Action(
                    type="notify",
                    rule_id=rule.id,
                    actor="athena",
                    recipients=[email],
                    clients=clients,
                    text=text,
                    delivery="now",
                    mode=rule.mode,
                    item_key=digest_key(rule.id, email, day),
                    sources=[
                        Source(
                            name=rule.source or rule.id, as_of=as_of or now - timedelta(days=365)
                        )
                    ],
                    payload={"scheduled_digest": True},
                )
            )
            if result.refused:
                log.warning(
                    "digest refused",
                    extra={"rule": rule.id, "reason": (result.reason or "").split(":")[0]},
                )
                continue
            with app.db.session() as s:
                for row in s.scalars(select(DigestItem).where(DigestItem.id.in_(item_ids))):
                    row.sent_at = now
            sent += 1
    return sent
