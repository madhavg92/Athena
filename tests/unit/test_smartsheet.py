from datetime import UTC, datetime

import httpx
import pytest

from athena.connectors.base import NotConfigured, fixture_anchor
from athena.connectors.http import ReadOnlyClient
from athena.connectors.smartsheet import SmartsheetConnector

ANCHOR = fixture_anchor()


def test_fixture_tasks(cfg) -> None:
    rows = SmartsheetConnector(cfg, clock=lambda: ANCHOR, run_mode="fixture").read("tasks")
    assert len(rows) == 30
    assert all(r.source == "smartsheet.tasks" and r.link for r in rows)
    assert "notes" not in rows[0].data
    assert all(isinstance(r.get("due"), datetime) for r in rows)
    phi_row = next(r for r in rows if r.suspect)
    assert "John Doe" not in phi_row.get("title") and "W998877665" not in phi_row.get("title")


def test_fixture_filter_by_client(cfg) -> None:
    rows = SmartsheetConnector(cfg, run_mode="fixture").read("tasks", client="cedar_family_clinic")
    assert len(rows) == 10 and {r.get("client") for r in rows} == {"cedar_family_clinic"}


SHEET = {
    "columns": [
        {"id": 1, "title": "Task Name"},
        {"id": 2, "title": "Assigned To"},
        {"id": 3, "title": "Due Date"},
        {"id": 4, "title": "Status"},
        {"id": 5, "title": "Modified"},
        {"id": 6, "title": "Patient Notes"},
    ],
    "rows": [
        {
            "id": 77,
            "permalink": "https://app.smartsheet.com/r/77",
            "modifiedAt": "2026-10-05T05:00:00Z",
            "cells": [
                {"columnId": 1, "value": "Post payments"},
                {"columnId": 2, "value": {"email": "dm.one@fixture.local"}},
                {"columnId": 3, "value": "2026-10-05T08:00:00Z"},
                {"columnId": 4, "value": "In Progress"},
                {"columnId": 6, "value": "secret"},
            ],
        }
    ],
}


def test_live_parses_sheet_with_mock(cfg) -> None:
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=SHEET)

    now = datetime(2026, 10, 5, 6, tzinfo=UTC)
    http = ReadOnlyClient(transport=httpx.MockTransport(handler))
    conn = SmartsheetConnector(cfg, clock=lambda: now, run_mode="live", http=http)
    rows = conn.read("tasks", client="northwind_ortho")
    assert len(seen) == 1 and seen[0].method == "GET"
    assert rows[0].get("owner") == "dm.one@fixture.local"
    assert rows[0].get("last_update") == datetime(2026, 10, 5, 5, tzinfo=UTC)
    assert rows[0].as_of == now and rows[0].link.endswith("/77")
    assert "Patient Notes" not in rows[0].data


def test_live_without_token(cfg, monkeypatch) -> None:
    monkeypatch.delenv("SMARTSHEET_TOKEN", raising=False)
    with pytest.raises(NotConfigured):
        SmartsheetConnector(cfg, run_mode="live").read("tasks")
