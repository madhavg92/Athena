"""absence: expected items that did not arrive within the grace time."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from croniter import croniter

from athena.checks import Hit
from athena.connectors.base import Record, parse_time
from athena.core.config import AbsenceCheck, CalendarExpected

LOOKBACK = timedelta(days=7)


def expected_items(check: AbsenceCheck, clients: list[str], now: datetime) -> list[dict]:
    """Expected items: from a static list (each with match_key value, client, due) or a calendar."""
    if isinstance(check.expected, CalendarExpected):
        cal = check.expected
        tz = ZoneInfo(cal.tz)
        items = []
        it = croniter(cal.cron, (now - LOOKBACK).astimezone(tz))
        while True:
            due = it.get_next(datetime)
            if due > now:
                break
            for client in clients:
                key = cal.key.format(client=client, date=due.date().isoformat())
                items.append({"key": key, "client": client, "due": due.astimezone(now.tzinfo)})
        return items
    return [
        {
            "key": str(e[check.match_key]),
            "client": e.get("client"),
            "due": parse_time(e.get("due")) or now,
        }
        for e in check.expected
    ]


def run(check: AbsenceCheck, arrived: list[Record], clients: list[str], now: datetime) -> list[Hit]:
    seen = {str(r.get(check.match_key)) for r in arrived}
    hits = []
    for item in expected_items(check, clients, now):
        if item["key"] not in seen and item["due"] + check.grace < now:
            hits.append(
                Hit(
                    key=item["key"],
                    severity=check.severity,
                    client=item["client"],
                    fields={"expected_key": item["key"], "due": item["due"]},
                )
            )
    return hits
