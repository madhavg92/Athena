"""JSON logging. In live mode, log only IDs, counts and timings, never record content."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime

_STD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        data.update({k: v for k, v in record.__dict__.items() if k not in _STD})
        if record.exc_info:
            data["exc"] = record.exc_info[0].__name__ if record.exc_info[0] else None
        return json.dumps(data, default=str)


def setup(level: str | None = None) -> None:
    root = logging.getLogger()
    if any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level or os.environ.get("ATHENA_LOG_LEVEL", "WARNING"))
