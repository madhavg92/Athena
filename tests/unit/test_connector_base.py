import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from athena.connectors.base import Connector, NotConfigured, mode


@pytest.fixture
def fixdir(tmp_path: Path) -> Path:
    (tmp_path / "meta.json").write_text(json.dumps({"anchor": "2026-01-01T00:00:00Z"}))
    (tmp_path / "things.json").write_text(
        json.dumps(
            [
                {
                    "id": 1,
                    "client": "a",
                    "title": "Call patient Jane Roe",
                    "when": "2026-01-01T01:00:00Z",
                    "secret": "x",
                },
                {
                    "id": 2,
                    "client": "b",
                    "title": "Post payments",
                    "when": "2025-12-31T00:00:00Z",
                    "secret": "y",
                    "as_of": "2025-12-30T00:00:00Z",
                },
            ]
        )
    )
    return tmp_path


class Things(Connector):
    NAME = "demo"
    DATASETS = {
        "things": {
            "file": "things.json",
            "allowed": ["id", "client", "title", "when"],
            "free_text": ["title"],
            "times": ["when"],
        }
    }


def test_allowed_fields_scrub_as_of(cfg, fixdir: Path) -> None:
    now = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    rows = Things(cfg, clock=lambda: now, fixtures=fixdir, run_mode="fixture").read("things")
    assert all("secret" not in r.data for r in rows)
    assert rows[0].source == "demo.things"
    assert "Jane Roe" not in rows[0].get("title") and rows[0].suspect
    assert rows[0].as_of == now - timedelta(minutes=5)
    assert rows[1].as_of == datetime(2025, 12, 30, tzinfo=UTC)  # record as_of wins


def test_fixture_times_shift_with_clock(cfg, fixdir: Path) -> None:
    now = datetime(2026, 3, 1, tzinfo=UTC)
    rows = Things(cfg, clock=lambda: now, fixtures=fixdir, run_mode="fixture").read("things")
    assert rows[0].get("when") == now + timedelta(hours=1)


def test_filters(cfg, fixdir: Path) -> None:
    rows = Things(cfg, fixtures=fixdir, run_mode="fixture").read("things", client="B")
    assert [r.get("id") for r in rows] == [2]


def test_live_not_configured(cfg, fixdir: Path) -> None:
    with pytest.raises(NotConfigured):
        Things(cfg, fixtures=fixdir, run_mode="live").read("things")


def test_mode_env(monkeypatch) -> None:
    monkeypatch.delenv("ATHENA_MODE", raising=False)
    assert mode() == "fixture"
    monkeypatch.setenv("ATHENA_MODE", "prod")
    with pytest.raises(ValueError):
        mode()
