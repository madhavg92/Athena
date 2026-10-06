import json
import logging

from athena.core.logs import JsonFormatter


def test_json_format() -> None:
    rec = logging.LogRecord("athena.x", logging.INFO, "f", 1, "tick", None, None)
    rec.rules = 2
    data = json.loads(JsonFormatter().format(rec))
    assert data["msg"] == "tick" and data["rules"] == 2 and data["level"] == "INFO"
