"""Duration strings such as `30m`, `4h`, `1d`."""

import re
from datetime import timedelta
from typing import Annotated, Any

from pydantic import BeforeValidator, PlainSerializer

_DURATION = re.compile(r"^\s*(\d+)\s*([smhdw])\s*$")
_UNITS = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}


def parse_duration(value: Any) -> timedelta:
    if isinstance(value, timedelta):
        return value
    match = _DURATION.match(str(value))
    if not match:
        raise ValueError(f"invalid duration {value!r}; use a number and s, m, h, d or w (e.g. 30m)")
    amount, unit = match.groups()
    return timedelta(**{_UNITS[unit]: int(amount)})


def format_duration(value: timedelta) -> str:
    seconds = int(value.total_seconds())
    for suffix, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds and seconds % size == 0:
            return f"{seconds // size}{suffix}"
    return f"{seconds}s"


Duration = Annotated[
    timedelta, BeforeValidator(parse_duration), PlainSerializer(format_duration, return_type=str)
]
