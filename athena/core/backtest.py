"""Backtest: replay history through the real rule loop with a moving clock.

Uses an in-memory database, live delivery to memory, and the rule's own cron, ladder and gateway.
History: fixtures/history/ (fixture mode). Live history is run by the user later.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from athena.app import App
from athena.connectors.base import FIXTURES, Record, fixture_anchor, parse_time
from athena.core import phi, scheduler
from athena.core.config import AthenaConfig
from athena.core.db import Alert, Database
from athena.core.gateway import Gateway, MemoryDeliverer
from athena.core.model import StubModel

STEP = timedelta(minutes=15)


def _latest(times: list[str], t: datetime) -> datetime | None:
    seen = [parse_time(x) for x in times if parse_time(x) <= t]
    return max(seen) if seen else None


def tasks_at(rows: list[dict], t: datetime) -> list[dict]:
    out = []
    for r in rows:
        created, done = parse_time(r["created_at"]), parse_time(r.get("completed_at"))
        if created > t or (done is not None and done < t - timedelta(hours=1)):
            continue
        out.append(
            {
                "task_id": r["task_id"],
                "client": r["client"],
                "title": r["title"],
                "owner": r["owner"],
                "due": parse_time(r["due"]),
                "status": "Complete" if done and done <= t else "In Progress",
                "last_update": _latest(r.get("updates", []), t) or created,
            }
        )
    return out


def tickets_at(rows: list[dict], t: datetime) -> list[dict]:
    out = []
    for r in rows:
        opened, closed = parse_time(r["opened_at"]), parse_time(r.get("closed_at"))
        if opened > t or (closed is not None and closed < t - timedelta(hours=1)):
            continue
        out.append(
            {
                "ticket_id": r["ticket_id"],
                "client": r["client"],
                "subject": r["subject"],
                "priority": r["priority"],
                "status": "closed" if closed and closed <= t else "open",
                "opened_at": opened,
                "last_reply_at": _latest(r.get("replies", []), t),
                "assignee": r["assignee"],
            }
        )
    return out


HISTORY: dict[str, tuple[str, Callable[[list[dict], datetime], list[dict]]]] = {
    "smartsheet.tasks": ("history/tasks.json", tasks_at),
    "cs_hub.tickets": ("history/tickets.json", tickets_at),
}


class HistorySources:
    """Duck-types `Sources.read` for the scheduler, at the replay clock."""

    def __init__(
        self, cfg: AthenaConfig, clock: Callable[[], datetime], fixtures: Path = FIXTURES
    ) -> None:
        self.cfg, self.clock = cfg, clock
        self.rows = {src: json.loads((fixtures / f).read_text()) for src, (f, _) in HISTORY.items()}

    def read(self, source: str, **filters: Any) -> list[Record]:
        if source not in HISTORY:
            raise KeyError(f"no history for source {source!r}; available: {', '.join(HISTORY)}")
        t = self.clock()
        rows = HISTORY[source][1](self.rows[source], t)
        out = []
        for row in rows:
            for f in ("title", "subject"):
                if isinstance(row.get(f), str):
                    row[f] = phi.scrub(row[f], self.cfg.internal_domains).text
            out.append(Record(source=source, as_of=t, data=row))
        return out


class BacktestReport(BaseModel):
    rule_id: str
    start: datetime
    end: datetime
    days: int
    alerts_opened: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)
    messages: int = 0
    per_person_per_day: dict[str, float] = Field(default_factory=dict)
    max_per_person_day: dict[str, int] = Field(default_factory=dict)
    labelled_wrong: int = 0
    wrong_rate: float | None = None

    def text(self) -> str:
        lines = [
            f"Backtest {self.rule_id}: {self.start:%Y-%m-%d} to {self.end:%Y-%m-%d} ({self.days} days, fixture history)",
            f"Alerts opened: {self.alerts_opened} ({', '.join(f'{k} {v}' for k, v in sorted(self.by_severity.items())) or '-'})",
            f"Messages that would be sent: {self.messages}",
            "Messages per person per day (average / max):",
        ]
        for p in sorted(self.per_person_per_day):
            lines.append(
                f"  {p:<28} {self.per_person_per_day[p]:>5.1f} / {self.max_per_person_day[p]}"
            )
        rate = f"{self.wrong_rate:.0%}" if self.wrong_rate is not None else "-"
        lines.append(f"Alerts labelled wrong in history: {self.labelled_wrong} (rate {rate})")
        return "\n".join(lines)


def run(
    cfg: AthenaConfig,
    rule_id: str,
    days: int,
    end: datetime | None = None,
    fixtures: Path = FIXTURES,
) -> BacktestReport:
    rule = cfg.rules[rule_id]
    if rule.is_question or rule.check is None:
        raise ValueError(f"{rule_id} is not a scheduled check rule")
    if rule.source not in HISTORY:
        raise ValueError(f"no history for source {rule.source!r}; available: {', '.join(HISTORY)}")
    end = end or fixture_anchor(fixtures)
    start = end - timedelta(days=days)
    live_rule = rule.model_copy(update={"mode": "live"})
    sim_cfg = cfg.model_copy(update={"rules": {**cfg.rules, rule_id: live_rule}})
    now = {"t": start}

    def clock() -> datetime:
        return now["t"]

    db, out = Database("sqlite://"), MemoryDeliverer()
    sources = HistorySources(sim_cfg, clock, fixtures)
    app = App(
        cfg=sim_cfg,
        db=db,
        gateway=Gateway(sim_cfg, db, out, clock),
        sources=sources,  # type: ignore[arg-type]
        model=StubModel(),
        clock=clock,
    )
    quiet = logging.getLogger("athena.core.scheduler")
    level = quiet.level
    quiet.setLevel(
        logging.ERROR
    )  # nights have no open tasks: "no data" on every tick is expected here
    last = None
    sent_day: Counter[tuple[str, str]] = Counter()
    while now["t"] <= end:
        before = len(out.sent)
        if scheduler.is_due(live_rule, last, now["t"]):
            scheduler.run_rule(app, live_rule)
            last = now["t"]
        app.gateway.release_held()
        for person, _, _ in out.sent[before:]:
            sent_day[(person, now["t"].date().isoformat())] += 1
        now["t"] += STEP
    quiet.setLevel(level)

    with db.session() as s:
        alerts = list(s.scalars(select(Alert).where(Alert.rule_id == rule_id)))
    labels = json.loads((fixtures / "history/labels.json").read_text())
    wrong_keys = {
        lb["item_key"]
        for lb in labels
        if lb["verdict"] == "wrong" and lb["rule_id"] in (rule_id, "*")
    }
    per_person: dict[str, list[int]] = defaultdict(list)
    for (person, _), n in sent_day.items():
        per_person[person].append(n)
    report = BacktestReport(rule_id=rule_id, start=start, end=end, days=days)
    report.alerts_opened = len(alerts)
    report.by_severity = dict(Counter(a.severity for a in alerts))
    report.messages = len(out.sent)
    report.per_person_per_day = {p: round(sum(v) / days, 2) for p, v in per_person.items()}
    report.max_per_person_day = {p: max(v) for p, v in per_person.items()}
    report.labelled_wrong = sum(1 for a in alerts if a.item_key.split(":", 1)[-1] in wrong_keys)
    report.wrong_rate = round(report.labelled_wrong / len(alerts), 3) if alerts else None
    return report
