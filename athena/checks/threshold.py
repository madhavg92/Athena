"""threshold: lists of conditions per severity; all conditions in a list must hold; first severity wins.
Add a new op only here, with tests."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from athena.checks import Hit
from athena.connectors.base import Record, parse_time
from athena.core.config import Condition, ThresholdCheck
from athena.core.durations import parse_duration


def _num(a: Any, b: Any, f: Callable[[Any, Any], bool]) -> bool:
    if a is None or b is None:
        return False
    try:
        return f(float(a), float(b))
    except (TypeError, ValueError):
        return f(a, b) if type(a) is type(b) else False


def _time(value: Any, now: datetime) -> datetime | None:
    if value == "now":
        return now
    try:
        return parse_time(value)
    except (TypeError, ValueError):
        return None


def holds(cond: Condition, data: dict[str, Any], now: datetime) -> bool:
    v = data.get(cond.field)
    op, ref = cond.op, cond.value
    if op == "is_null":
        return v in (None, "")
    if op == "not_null":
        return v not in (None, "")
    if op == "eq":
        return _num(v, ref, lambda a, b: a == b) if not isinstance(ref, str) else str(v) == ref
    if op == "ne":
        return not (
            _num(v, ref, lambda a, b: a == b) if not isinstance(ref, str) else str(v) == ref
        )
    if op in ("lt", "lte", "gt", "gte"):
        fn = {
            "lt": lambda a, b: a < b,
            "lte": lambda a, b: a <= b,
            "gt": lambda a, b: a > b,
            "gte": lambda a, b: a >= b,
        }
        return _num(v, ref, fn[op])
    if op == "lt_field":
        return _num(v, data.get(ref), lambda a, b: a < b)
    if op == "gt_field":
        return _num(v, data.get(ref), lambda a, b: a > b)
    t = _time(v, now)
    if t is None:
        return False
    if op == "before":
        r = _time(ref, now)
        return r is not None and t < r
    if op == "after":
        r = _time(ref, now)
        return r is not None and t > r
    if op == "within":
        return now <= t <= now + parse_duration(ref)
    if op == "older_than":
        return t < now - parse_duration(ref)
    raise ValueError(f"unknown op {op!r}")


def run(check: ThresholdCheck, records: list[Record], now: datetime) -> list[Hit]:
    hits = []
    for rec in records:
        for severity, conditions in check.severities.items():
            if all(holds(c, rec.data, now) for c in conditions):
                key = str(rec.get(check.key))
                hits.append(
                    Hit(key=key, severity=severity, client=rec.get("client"), fields=dict(rec.data))
                )
                break
    return hits
