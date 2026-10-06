from datetime import timedelta

import pytest

from athena.app import build
from athena.core import meetings, money
from athena.core.db import Database
from athena.tools.base import ToolContext
from athena.tools.registry import call

HL = "hl.key@fixture.local"


@pytest.fixture
def ctx(cfg, anchor):
    app = build(cfg=cfg, db=Database("sqlite://"), clock=lambda: anchor, run_mode="fixture")
    return ToolContext(cfg=cfg, gateway=app.gateway, sources=app.sources, actor=HL)


def test_at_risk_ranked_and_computed(cfg, ctx, anchor) -> None:
    risks = money.at_risk(cfg, ctx.sources, ["northwind_ortho", "bluefield_imaging"], anchor)
    assert risks == sorted(risks, key=lambda r: -r.amount_usd)
    top = risks[0]
    assert top.kind == "appeal" and top.reason_code == "CO-197" and top.payer.startswith("Payer B")
    assert top.expected_recovery_usd == round(top.amount_usd * 0.70)
    assert top.fee_at_risk_usd == round(top.expected_recovery_usd * 5.0 / 100)
    assert all(0 <= r.days_left <= 14 for r in risks)
    assert all(r.client in ("northwind_ortho", "bluefield_imaging") for r in risks)


def test_biggest_move_names_who_has_room(cfg, ctx, anchor) -> None:
    clients = ["northwind_ortho", "bluefield_imaging"]
    move = money.biggest_move(
        cfg, ctx.sources, money.at_risk(cfg, ctx.sources, clients, anchor), clients
    )
    assert move.risk.reason_code == "CO-197" and move.who == "Analyst B1" and "$22,400" in move.text


def test_tools_scope_and_access(cfg, ctx, anchor) -> None:
    r = call(ctx, "get_money_at_risk", {})
    assert r.ok and r.records[0]["total_at_risk_usd"] > 0 and r.records[0]["biggest_move"]
    assert (
        "not in your scope"
        in call(ctx, "get_money_at_risk", {"client": "Cedar Family Clinic"}).error
    )
    econ = call(ctx, "get_client_economics", {"client": "Northwind"})
    assert (
        econ.records[-1]["revenue_per_fte_usd"] == round(13200 / 3.5)
        and econ.records[-1]["margin_pct"] == 62.9
    )
    dm = ToolContext(
        cfg=cfg, gateway=ctx.gateway, sources=ctx.sources, actor="dm.one@fixture.local"
    )
    assert "not available to your persona" in call(dm, "get_client_economics", {}).error


def test_meetings_and_briefs(cfg, ctx, anchor) -> None:
    week = meetings.upcoming(ctx.sources, HL, anchor - timedelta(hours=1))
    assert [m["title"] for m in week] == [
        "Weekly hub ops review",
        "Northwind weekly call",
        "Bluefield quarterly review",
    ]
    nw = call(ctx, "get_meetings", {"title": "Northwind"}).records[0]
    assert (
        nw["client"] == "Northwind Orthopedics"
        and nw["tickets_waiting_on_us"]
        and nw["commitments"]
        and nw["decisions"]
    )
    assert {c["direction"] for c in nw["changes"]} <= {"better", "worse", "same"}
    ops = call(ctx, "get_meetings", {"title": "ops review"}).records[0]
    assert ops["money_at_risk_usd"] > 0 and any("Analyst N2" in g for g in ops["staffing_gaps"])
    assert len(ops["decisions"]) == 3
    assert (
        meetings.upcoming(ctx.sources, "dm.one@fixture.local", anchor) == []
    )  # only your own calendar
