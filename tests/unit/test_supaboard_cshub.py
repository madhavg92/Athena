from datetime import timedelta

import pytest

from athena.connectors.base import NotConfigured, fixture_anchor
from athena.connectors.cshub import CSHubConnector
from athena.connectors.supaboard import SupaboardConnector, latest

ANCHOR = fixture_anchor()


def test_metrics_fixture(cfg) -> None:
    rows = SupaboardConnector(cfg, clock=lambda: ANCHOR, run_mode="fixture").read(
        "metrics", client="northwind_ortho", metric="backlog"
    )
    assert len(rows) == 60
    assert rows[0].source == "supaboard.metrics" and rows[0].as_of == ANCHOR - timedelta(hours=3)
    last = latest(rows)
    assert len(last) == 1 and last[0].get("date") == (ANCHOR - timedelta(days=1)).date().isoformat()
    assert last[0].get("client_metric") == "northwind_ortho:backlog"


def test_metric_dates_shift(cfg) -> None:
    later = ANCHOR + timedelta(days=10)
    rows = SupaboardConnector(cfg, clock=lambda: later, run_mode="fixture").read("metrics")
    assert max(r.get("date") for r in rows) == (later - timedelta(days=1)).date().isoformat()


def test_tickets_and_health(cfg) -> None:
    conn = CSHubConnector(cfg, clock=lambda: ANCHOR, run_mode="fixture")
    tickets = conn.read("tickets", client="bluefield_imaging", status="open")
    assert tickets and all(t.get("status") == "open" for t in tickets)
    health = {h.get("client"): h for h in conn.read("health")}
    assert ANCHOR - health["cedar_family_clinic"].as_of > timedelta(days=2)  # stale on purpose
    assert ANCHOR - health["northwind_ortho"].as_of == timedelta(hours=2)


@pytest.mark.parametrize("cls,ds", [(SupaboardConnector, "metrics"), (CSHubConnector, "tickets")])
def test_live_waits_for_gate(cfg, cls, ds, monkeypatch) -> None:
    for var in ("SUPABOARD_BASE_URL", "SUPABOARD_API_KEY", "CSHUB_BASE_URL", "CSHUB_API_KEY"):
        monkeypatch.setenv(var, "x")
    with pytest.raises(NotConfigured, match=r"G2|G3"):
        cls(cfg, run_mode="live").read(ds)
