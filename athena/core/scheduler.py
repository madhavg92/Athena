"""Scheduler tick and the rule loop. Runs every 15 minutes (Azure Functions timer, or `athena tick`).

For each due rule: read the source, check freshness, run the check (code, not AI), open/update/close
alerts, then let the ladder decide who gets a message. Every message goes through the gateway.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from croniter import croniter
from pydantic import BaseModel, Field
from sqlalchemy import select

from athena.app import App
from athena.checks import Hit, absence, threshold
from athena.connectors.base import NotConfigured, Record
from athena.core import ladder
from athena.core.config import AbsenceCheck, CronTrigger, Rule
from athena.core.db import Alert, RuleState, as_utc
from athena.core.durations import format_duration
from athena.core.gateway import Action, Source
from athena.core.templates import write_message

log = logging.getLogger(__name__)
TICK = timedelta(minutes=15)


class RuleRun(BaseModel):
    rule_id: str
    ran: bool = True
    stale: bool = False
    reason: str | None = None
    hits: int = 0
    opened: int = 0
    closed: int = 0
    messages: dict[str, int] = Field(default_factory=dict)  # receipt status -> count


# ---------------------------------------------------------------- schedule


def is_due(rule: Rule, last_run: datetime | None, now: datetime) -> bool:
    if not isinstance(rule.trigger, CronTrigger):
        return False
    tz = ZoneInfo(rule.trigger.tz)
    prev = (
        croniter(rule.trigger.cron, (now + timedelta(seconds=1)).astimezone(tz))
        .get_prev(datetime)
        .astimezone(now.tzinfo)
    )
    if last_run is None:
        return now - prev < TICK  # first run only near a scheduled time
    return as_utc(last_run) < prev


def rule_state(app: App, rule_id: str) -> RuleState:
    with app.db.session() as s:
        row = s.get(RuleState, rule_id)
        if row is None:
            row = RuleState(rule_id=rule_id)
            s.add(row)
            s.flush()
        return row


def effective_phase(app: App, rule: Rule) -> int:
    state = rule_state(app, rule.id)
    return state.phase if state.phase is not None else rule.phase


def _set_state(app: App, rule_id: str, **fields: Any) -> None:
    with app.db.session() as s:
        row = s.get(RuleState, rule_id) or RuleState(rule_id=rule_id)
        for k, v in fields.items():
            setattr(row, k, v)
        row.updated_at = app.clock()
        s.add(row)


# ---------------------------------------------------------------- payload


def payload_for(app: App, rule: Rule, alert: Alert) -> dict[str, Any]:
    """Structured payload built in code. The model writes text from this only."""
    now = app.clock()
    fields = dict(alert.payload or {})
    client = app.cfg.owner_map.clients.get(alert.client or "")
    out: dict[str, Any] = {
        "rule": rule.name,
        "item_key": alert.item_key.split(":", 1)[-1],
        "severity": alert.severity,
        "severity_label": alert.severity.replace("_", " ").capitalize(),
        "client_name": client.name if client else (alert.client or "-"),
        "age": _age(now - as_utc(alert.opened_at)),
    }
    for k, v in fields.items():
        if isinstance(v, str) and k.endswith(("_at", "due", "update", "as_of")):
            try:
                v = datetime.fromisoformat(v)
            except ValueError:
                pass
        if isinstance(v, datetime):
            tz = app.cfg.work_hours_of(
                client.role(rule.ladder[0].to) if client and rule.ladder else ""
            )[1]
            v = v.astimezone(ZoneInfo(tz)).strftime("%d %b %H:%M")
        out.setdefault(k, v)
    owner = app.cfg.person(str(out.get("owner", "")))
    if owner:
        out["owner"] = owner.name
    return out


def _age(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"


def _jsonable(fields: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in fields.items()}


# ---------------------------------------------------------------- rule run


def read_records(app: App, rule: Rule) -> list[Record]:
    clients = rule.clients or list(app.cfg.owner_map.clients)
    records = app.sources.read(rule.source)
    return [r for r in records if r.get("client") in clients or r.get("client") is None]


def run_checks(app: App, rule: Rule, records: list[Record], now: datetime) -> list[Hit]:
    if isinstance(rule.check, AbsenceCheck):
        arrived = app.sources.read(rule.check.arrived_source)
        return absence.run(
            rule.check, arrived, rule.clients or list(app.cfg.owner_map.clients), now
        )
    return threshold.run(rule.check, records, now)


def run_rule(app: App, rule: Rule) -> RuleRun:
    now = app.clock()
    result = RuleRun(rule_id=rule.id)
    try:
        records = read_records(app, rule)
    except NotConfigured as exc:
        _set_state(app, rule.id, last_run_at=now)
        return RuleRun(rule_id=rule.id, stale=True, reason=f"source not available: {exc}")

    newest = max((r.as_of for r in records), default=None)
    if newest is None or now - newest > rule.data_max_age:
        log.warning("stale", extra={"rule": rule.id})
        _set_state(app, rule.id, stale=True, last_run_at=now)
        result.stale = True
        result.reason = "no data" if newest is None else f"newest as_of {newest:%Y-%m-%d %H:%M} UTC"
        return result

    hits = run_checks(app, rule, records, now)
    result.hits = len(hits)
    keys = {f"{rule.id}:{h.key}" for h in hits}
    with app.db.session() as s:
        open_alerts = {
            a.item_key: a
            for a in s.scalars(select(Alert).where(Alert.rule_id == rule.id, Alert.state == "open"))
        }
        for hit in hits:
            key = f"{rule.id}:{hit.key}"
            alert = open_alerts.get(key)
            if alert is None:
                s.add(
                    Alert(
                        rule_id=rule.id,
                        item_key=key,
                        client=hit.client,
                        severity=hit.severity,
                        opened_at=now,
                        payload=_jsonable(hit.fields),
                        last_sent_at={},
                        sends_count={},
                    )
                )
                result.opened += 1
            else:
                kept = {
                    k: v for k, v in (alert.payload or {}).items() if k.startswith("_")
                }  # ack, snooze
                alert.severity, alert.payload = hit.severity, {**_jsonable(hit.fields), **kept}
        for key, alert in open_alerts.items():
            if key not in keys:
                alert.state, alert.closed_at = "closed", now
                result.closed += 1
    _set_state(app, rule.id, stale=False, last_run_at=now)
    result.messages = send_due(app, rule, newest)
    return result


def _prefix(kind: str, step: int, rule: Rule) -> str:
    if kind == "reminder":
        return "Reminder: "
    if kind == "first" and step > 0:
        return f"Escalation (still open after {format_duration(rule.ladder[step].after)}): "
    return ""


def send_due(app: App, rule: Rule, as_of: datetime) -> dict[str, int]:
    now = app.clock()
    counts: dict[str, int] = {}
    phase = effective_phase(app, rule)
    writer = rule.message.writer if rule.message else "template"
    template = rule.message.template if rule.message else "default"
    with app.db.session() as s:
        alerts = list(
            s.scalars(select(Alert).where(Alert.rule_id == rule.id, Alert.state == "open"))
        )
    for alert in alerts:
        step, sends = ladder.due_sends(app.cfg, rule, alert, now)
        if not sends:
            continue
        payload = payload_for(app, rule, alert)
        text, t_in, t_out = write_message(app.model, app.cfg.root, template, payload, writer)
        for person, kind in sends:
            action = Action(
                type="notify",
                rule_id=rule.id,
                actor="athena",
                recipients=[person],
                clients=[alert.client] if alert.client else [],
                text=_prefix(kind, step, rule) + text,
                payload=payload,
                delivery=rule.delivery,
                sources=[Source(name=rule.source or rule.id, as_of=as_of)],
                phase=phase,
                mode=rule.mode,
                item_key=alert.item_key,
                tokens_in=t_in,
                tokens_out=t_out,
            )
            res = app.gateway.submit(action)
            status = res.per_recipient.get(person, "refused")
            counts[status] = counts.get(status, 0) + 1
            if res.refused:
                log.info(
                    "alert refused",
                    extra={"rule": rule.id, "reason": (res.reason or "").split(":")[0]},
                )
                continue
            with app.db.session() as s:
                row = s.get(Alert, alert.id)
                row.ladder_step = step
                row.sends_count = {
                    **(row.sends_count or {}),
                    person: int((row.sends_count or {}).get(person, 0)) + 1,
                }
                row.last_sent_at = {**(row.last_sent_at or {}), person: now.isoformat()}
    return counts


# ---------------------------------------------------------------- tick


def tick(app: App, force: list[str] | None = None) -> dict[str, Any]:
    """Run due rules once, release held messages, send due digests, check demotion."""
    from athena.core import digest, review
    from athena.reports import wbr

    now = app.clock()
    runs: list[RuleRun] = []
    for rule in app.cfg.rules.values():
        if rule.is_question:
            continue
        due = (force and rule.id in force) or (
            not force and is_due(rule, rule_state(app, rule.id).last_run_at, now)
        )
        if not due:
            continue
        if rule.action == "draft":
            runs.append(wbr.run_rule(app, rule))
        else:
            runs.append(run_rule(app, rule))
    released = app.gateway.release_held()
    digests = digest.send_due_digests(app)
    demoted = review.apply_demotion(app)
    log.info("tick", extra={"rules": len(runs), "released": released, "digests": digests})
    return {
        "runs": [r.model_dump() for r in runs],
        "released": released,
        "digests": digests,
        "demoted": demoted,
    }
