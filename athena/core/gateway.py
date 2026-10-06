"""The gateway. Every action passes these checks, in this order, then is delivered and receipted.

1 kill switch, 2 action type, 3 recipients internal, 4 scope, 5 freshness, 6 PHI lint,
7 message limit, 8 work hours, 9 mode.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field
from sqlalchemy import func, select

from athena.core import phi
from athena.core.config import AthenaConfig
from athena.core.db import Database, DigestItem, Receipt, as_utc, utcnow
from athena.core.killswitch import blocked_by

log = logging.getLogger(__name__)

STALE_MARK = "Data is not current"
MAX_NOTIFY_PER_PERSON = 2


class Source(BaseModel):
    name: str
    ref: str | None = None
    as_of: datetime


class Action(BaseModel):
    type: Literal["answer", "notify", "draft", "write"]
    rule_id: str
    actor: str
    recipients: list[str] = []
    clients: list[str] = []
    text: str = ""
    payload: dict[str, Any] = {}
    delivery: Literal["now", "digest"] = "now"
    sources: list[Source] = []
    phase: int = 1
    mode: Literal["shadow", "live"] = "live"
    item_key: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class GatewayResult(BaseModel):
    status: Literal["ok", "refused"]
    reason: str | None = None
    per_recipient: dict[str, str] = Field(default_factory=dict)  # email -> receipt status
    receipt_ids: list[int] = Field(default_factory=list)

    @property
    def refused(self) -> bool:
        return self.status == "refused"


class Deliverer(Protocol):
    def send(self, recipient: str, text: str, action: Action) -> None: ...


class MemoryDeliverer:
    """Fixture-mode delivery: keeps messages in memory (and in receipts)."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str, Action]] = []

    def send(self, recipient: str, text: str, action: Action) -> None:
        self.sent.append((recipient, text, action))


def next_work_start(cfg: AthenaConfig, email: str, now: datetime) -> datetime | None:
    """None if `now` is inside the person's work hours, else the next work start (UTC)."""
    hours, tz = cfg.work_hours_of(email)
    local = now.astimezone(ZoneInfo(tz))
    if hours.contains(local.time()):
        return None
    start = local.replace(hour=hours.start.hour, minute=hours.start.minute, second=0, microsecond=0)
    if start <= local:
        start += timedelta(days=1)
    return start.astimezone(now.tzinfo)


class Gateway:
    def __init__(
        self,
        cfg: AthenaConfig,
        db: Database,
        deliverer: Deliverer | None = None,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.cfg = cfg
        self.db = db
        self.deliverer = deliverer or MemoryDeliverer()
        self.clock = clock

    # ---- checks usable on their own (tool calls use these) ----

    def scope_problem(self, people: list[str], clients: list[str]) -> str | None:
        for person in people:
            scope = set(self.cfg.scope_of(person))
            for client in clients:
                if client not in scope:
                    return f"scope: {client} is not in the scope of {person}"
        return None

    def authorize_tool(self, actor: str, rule_id: str, clients: list[str]) -> str | None:
        """Kill switch and scope check for a read-only tool call. None = allowed."""
        return blocked_by(self.db, rule_id, [actor]) or self.scope_problem([actor], clients)

    # ---- the pipeline ----

    def _first_problem(self, a: Action, now: datetime) -> str | None:
        # 1 kill switch
        reason = blocked_by(self.db, a.rule_id, [a.actor, *a.recipients])
        if reason:
            return reason
        # 2 action type
        if a.type == "write":
            return "action type: write is disabled in this build"
        # 3 recipients internal
        domains = self.cfg.internal_domains
        for r in a.recipients:
            domain = r.rsplit("@", 1)[-1].lower() if "@" in r else ""
            if domain not in domains:
                return f"recipient not internal: {r}"
        if not a.recipients:
            return "no recipients"
        # 4 scope
        people = list(a.recipients) + ([a.actor] if a.type == "answer" else [])
        reason = self.scope_problem(people, a.clients)
        if reason:
            return reason
        # 5 freshness
        rule = self.cfg.rules.get(a.rule_id)
        if rule is not None and STALE_MARK.lower() not in a.text.lower():
            for src in a.sources:
                age = now - as_utc(src.as_of)
                if age > rule.data_max_age:
                    return f"freshness: {src.name} as_of {src.as_of:%Y-%m-%d %H:%M} UTC is older than {rule.data_max_age}"
        # 6 PHI lint
        found = phi.lint(a.text, domains)
        if found:
            return f"phi lint: {', '.join(found)}"
        # 7 message limit
        if a.type == "notify" and a.delivery == "now" and a.item_key:
            for r in a.recipients:
                if self.notify_count(a.item_key, r) >= MAX_NOTIFY_PER_PERSON:
                    return f"message limit: {r} already has {MAX_NOTIFY_PER_PERSON} messages for {a.item_key}"
        return None

    def notify_count(self, item_key: str, recipient: str) -> int:
        with self.db.session() as s:
            return s.scalar(
                select(func.count(Receipt.id)).where(
                    Receipt.item_key == item_key,
                    Receipt.recipient == recipient,
                    Receipt.action_type == "notify",
                    Receipt.status.in_(["sent", "held", "shadow", "read", "acted"]),
                )
            )

    def submit(self, a: Action) -> GatewayResult:
        now = self.clock()
        reason = self._first_problem(a, now)
        if reason:
            ids = [self._receipt(a, r, "refused", reason, now) for r in (a.recipients or [None])]
            log.info("gateway refused", extra={"rule": a.rule_id, "reason": reason.split(":")[0]})
            return GatewayResult(status="refused", reason=reason, receipt_ids=ids)

        result = GatewayResult(status="ok")
        for r in a.recipients:
            status, deliver_at = self._route(a, r, now)
            result.receipt_ids.append(self._receipt(a, r, status, None, now, deliver_at))
            result.per_recipient[r] = status
        return result

    def _route(self, a: Action, recipient: str, now: datetime) -> tuple[str, datetime | None]:
        if a.type == "notify" and a.delivery == "digest":
            # queued even in shadow, so a shadow digest shows what a live one would hold
            with self.db.session() as s:
                s.add(
                    DigestItem(
                        user=recipient,
                        rule_id=a.rule_id,
                        item_key=a.item_key,
                        text=a.text,
                        created_at=now,
                    )
                )
            return ("shadow" if a.mode == "shadow" else "queued"), None
        # 9 mode: shadow goes to the review list, not to people
        if a.mode == "shadow":
            return "shadow", None
        # 8 work hours
        if a.type == "notify" and a.delivery == "now":
            start = next_work_start(self.cfg, recipient, now)
            if start is not None:
                return "held", start
        self.deliverer.send(recipient, a.text, a)
        return "sent", None

    def release_held(self) -> int:
        """Deliver held messages whose time has come. Returns the number sent."""
        now = self.clock()
        sent = 0
        with self.db.session() as s:
            rows = s.scalars(select(Receipt).where(Receipt.status == "held")).all()
            for row in rows:
                if as_utc(row.deliver_at) and as_utc(row.deliver_at) <= now:
                    if blocked_by(self.db, row.rule_id, [row.recipient]):
                        continue
                    action = Action(
                        type="notify",
                        rule_id=row.rule_id or "",
                        actor=row.actor,
                        recipients=[row.recipient],
                        text=row.output or "",
                        item_key=row.item_key,
                    )
                    self.deliverer.send(row.recipient, row.output or "", action)
                    row.status = "sent"
                    sent += 1
        return sent

    def _receipt(
        self,
        a: Action,
        recipient: str | None,
        status: str,
        reason: str | None,
        now: datetime,
        deliver_at: datetime | None = None,
    ) -> int:
        with self.db.session() as s:
            row = Receipt(
                time=now,
                actor=a.actor,
                recipient=recipient,
                rule_id=a.rule_id,
                action_type=a.type,
                delivery=a.delivery,
                mode=a.mode,
                sources=[src.model_dump(mode="json") for src in a.sources],
                output=a.text,
                status=status,
                reason=reason,
                tokens_in=a.tokens_in,
                tokens_out=a.tokens_out,
                cost_usd=a.cost_usd,
                latency_ms=a.latency_ms,
                item_key=a.item_key,
                deliver_at=deliver_at,
            )
            s.add(row)
            s.flush()
            return row.id
