from datetime import UTC, datetime, timedelta

import pytest

from athena.checks import absence, threshold
from athena.connectors.base import Record
from athena.core.config import AbsenceCheck, Condition, ThresholdCheck, load_config

NOW = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)


def rec(**data) -> Record:
    return Record(source="t.t", as_of=NOW, data=data)


H = timedelta(hours=1)
CASES = [
    # field value, op, ref, expected
    (5, "eq", 5, True),
    (5, "eq", 6, False),
    ("Complete", "eq", "Complete", True),
    ("Open", "ne", "Complete", True),
    ("Complete", "ne", "Complete", False),
    (3, "lt", 4, True),
    (4, "lt", 4, False),
    (4, "lte", 4, True),
    (5, "gt", 4, True),
    (4, "gt", 4, False),
    (4, "gte", 4, True),
    (None, "gt", 1, False),
    (NOW - H, "before", "now", True),
    (NOW + H, "before", "now", False),
    (NOW + H, "after", "now", True),
    (NOW - H, "after", "2026-10-05T04:00:00Z", True),
    (NOW + 2 * H, "within", "4h", True),
    (NOW + 5 * H, "within", "4h", False),
    (NOW - H, "within", "4h", False),
    (NOW - 3 * H, "older_than", "2h", True),
    (NOW - H, "older_than", "2h", False),
    (None, "older_than", "2h", False),
    (None, "is_null", None, True),
    ("", "is_null", None, True),
    ("x", "not_null", None, True),
    (None, "not_null", None, False),
]


@pytest.mark.parametrize("value,op,ref,expected", CASES)
def test_ops(value, op, ref, expected) -> None:
    assert threshold.holds(Condition(field="f", op=op, value=ref), {"f": value}, NOW) is expected


@pytest.mark.parametrize(
    "a,b,op,expected",
    [
        (1, 2, "lt_field", True),
        (3, 2, "lt_field", False),
        (3, 2, "gt_field", True),
        (None, 2, "gt_field", False),
    ],
)
def test_field_ops(a, b, op, expected) -> None:
    assert (
        threshold.holds(Condition(field="a", op=op, value="b"), {"a": a, "b": b}, NOW) is expected
    )


def test_first_severity_wins_with_r2() -> None:
    check = load_config().rules["R2"].check
    late = rec(task_id="T1", client="c", due=NOW - H, status="In Progress", last_update=NOW - 5 * H)
    risk = rec(task_id="T2", client="c", due=NOW + H, status="Not Started", last_update=NOW - 3 * H)
    fresh = rec(
        task_id="T3", client="c", due=NOW + H, status="Not Started", last_update=NOW - 0.5 * H
    )
    done = rec(task_id="T4", client="c", due=NOW - H, status="Complete", last_update=NOW)
    hits = threshold.run(check, [late, risk, fresh, done], NOW)
    assert [(h.key, h.severity) for h in hits] == [("T1", "late"), ("T2", "at_risk")]


def test_threshold_r3_lt_field() -> None:
    check = ThresholdCheck(
        type="threshold",
        key="k",
        severities={"below": [Condition(field="actual", op="lt_field", value="target")]},
    )
    hits = threshold.run(
        check, [rec(k="a", actual=1, target=2), rec(k="b", actual=3, target=2)], NOW
    )
    assert [h.key for h in hits] == ["a"]


def test_absence_list() -> None:
    check = AbsenceCheck(
        type="absence",
        expected=[
            {"report": "r1", "client": "c", "due": "2026-10-05T01:00:00Z"},
            {"report": "r2", "client": "c", "due": "2026-10-05T05:30:00Z"},
        ],
        arrived_source="x.y",
        match_key="report",
        grace="1h",
    )
    hits = absence.run(check, [], ["c"], NOW)
    assert [h.key for h in hits] == ["r1"]  # r2 still within grace
    assert absence.run(check, [rec(report="r1")], ["c"], NOW) == []


def test_absence_calendar() -> None:
    check = AbsenceCheck(
        type="absence",
        expected={"cron": "0 9 * * 1-5", "key": "{client}:{date}", "tz": "Asia/Kolkata"},
        arrived_source="x.y",
        match_key="report",
        grace="2h",
    )
    arrived = [rec(report="a:2026-10-02")]
    keys = [h.key for h in absence.run(check, arrived, ["a"], NOW)]
    # Mon 2026-10-05 09:00 IST = 03:30 UTC, +2h grace = 05:30 < 06:00 -> missing; Fri 10-02 arrived
    assert "a:2026-10-05" in keys and "a:2026-10-02" not in keys and "a:2026-09-29" in keys
