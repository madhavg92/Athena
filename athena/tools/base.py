"""Shared tool types. Tools are read only, take the user's scope and return records with sources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from athena.connectors.base import Record
from athena.connectors.registry import Sources
from athena.core.config import AthenaConfig
from athena.core.gateway import Gateway, Source


@dataclass
class ToolContext:
    cfg: AthenaConfig
    gateway: Gateway
    sources: Sources
    actor: str
    rule_id: str = "R1"
    user_assertion: str | None = None  # Teams SSO token for delegated search (live)

    @property
    def now(self) -> datetime:
        return self.gateway.clock()

    @property
    def tz(self) -> str:
        return self.cfg.work_hours_of(self.actor)[1]


class ToolResult(BaseModel):
    name: str
    ok: bool
    client: str | None = None
    records: list[dict[str, Any]] = []
    sources: list[Source] = []
    stale: bool = False
    error: str | None = None
    meta: dict[str, Any] = {}  # labels for the model: client_name, metric

    @property
    def has_data(self) -> bool:
        return self.ok and bool(self.records)

    def for_model(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": self.ok, **self.meta}
        if self.error:
            out["error"] = self.error
        else:
            out["records"] = self.records
            out["as_of"] = [f"{s.name}: {s.as_of:%Y-%m-%d %H:%M} UTC" for s in self.sources]
            if self.stale:
                out["warning"] = "Data is not current. Give the as_of time."
        return out


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    fn: Callable[..., ToolResult]
    needs_client: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


CLIENT_PARAM = {
    "type": "string",
    "description": "Client name or key, e.g. 'Northwind Orthopedics'.",
}


def fmt_time(value: Any, tz: str) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")
    return value


def to_model_rows(records: list[Record], fields: list[str], tz: str) -> list[dict[str, Any]]:
    return [{f: fmt_time(r.get(f), tz) for f in fields if f in r.data} for r in records]


def sources_of(records: list[Record], name: str | None = None) -> list[Source]:
    """One Source per distinct source name (oldest as_of wins, so staleness is never hidden)."""
    oldest: dict[str, Record] = {}
    for r in records:
        if r.source not in oldest or r.as_of < oldest[r.source].as_of:
            oldest[r.source] = r
    return [Source(name=name or r.source, ref=_ref(r), as_of=r.as_of) for r in oldest.values()]


def _ref(record: Record) -> str | None:
    if record.source == "smartsheet.tasks" and record.link:
        return record.link.split("?")[0]
    return record.link


def is_stale(ctx: ToolContext, sources: list[Source]) -> bool:
    rule = ctx.cfg.rules.get(ctx.rule_id)
    if rule is None:
        return False
    return any(ctx.now - s.as_of > rule.data_max_age for s in sources)
