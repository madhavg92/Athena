import pytest

from athena.connectors.base import fixture_anchor
from athena.connectors.registry import Sources
from athena.core.gateway import Gateway
from athena.core.killswitch import set_switch
from athena.tools.base import ToolContext
from athena.tools.registry import TOOLS, call, schemas

ANCHOR = fixture_anchor()


@pytest.fixture
def ctx(cfg, db):
    clock = lambda: ANCHOR  # noqa: E731
    return ToolContext(
        cfg=cfg,
        gateway=Gateway(cfg, db, clock=clock),
        sources=Sources(cfg, clock=clock, run_mode="fixture"),
        actor="hl.key@fixture.local",
    )


def test_tools_with_schemas() -> None:
    assert set(TOOLS) == {
        "get_tasks",
        "get_metrics",
        "get_tickets",
        "search_documents",
        "get_owner",
        "get_client_profile",
        "get_denials",
        "get_ar_aging",
        "get_task_history",
        "get_team",
        "get_client_activity",
        "get_my_alerts",
    }
    for s in schemas():
        assert s["type"] == "function" and s["function"]["parameters"]["type"] == "object"
        if s["function"]["name"] != "get_my_alerts":
            assert "client" in s["function"]["parameters"]["required"]


def test_get_tasks_by_name(ctx) -> None:
    r = call(ctx, "get_tasks", {"client": "Northwind Orthopedics"})
    assert r.ok and r.client == "northwind_ortho"
    assert all(row["status"] != "Complete" for row in r.records)
    assert any(row["late"] for row in r.records)
    assert r.sources[0].name == "smartsheet.tasks" and not r.stale


def test_scope_refused(ctx) -> None:
    r = call(ctx, "get_tasks", {"client": "Cedar Family Clinic"})
    assert not r.ok and "not in your scope" in r.error


def test_kill_switch_refuses_tool(ctx, db) -> None:
    set_switch(db, "user", "hl.key@fixture.local", True, "ops")
    assert "kill switch" in call(ctx, "get_owner", {"client": "northwind_ortho"}).error


def test_unknown_client_tool_and_args(ctx) -> None:
    assert "unknown client" in call(ctx, "get_tasks", {"client": "Acme"}).error
    assert "unknown tool" in call(ctx, "drop_tables", {}).error
    assert (
        "unknown arguments" in call(ctx, "get_owner", {"client": "northwind_ortho", "x": 1}).error
    )
    assert "missing" in call(ctx, "get_metrics", {"client": "northwind_ortho"}).error
    assert (
        "unknown tool"
        in call(ctx, "get_tasks", {"client": "northwind_ortho"}, allowed=["get_owner"]).error
    )


def test_metrics(ctx) -> None:
    r = call(ctx, "get_metrics", {"client": "northwind_ortho", "metric": "backlog"})
    assert len(r.records) == 1 and r.records[0]["target"] == 300.0 and "meaning" in r.records[0]
    week = call(
        ctx,
        "get_metrics",
        {"client": "northwind_ortho", "metric": "backlog", "period": "last_7_days"},
    )
    assert len(week.records) == 7
    assert (
        "unknown metric"
        in call(ctx, "get_metrics", {"client": "northwind_ortho", "metric": "joy"}).error
    )


def test_tickets_health_and_stale(cfg, db) -> None:
    clock = lambda: ANCHOR  # noqa: E731
    ctx = ToolContext(
        cfg=cfg,
        gateway=Gateway(cfg, db, clock=clock),
        sources=Sources(cfg, clock=clock, run_mode="fixture"),
        actor="hl.small@fixture.local",
    )
    r = call(ctx, "get_tickets", {"client": "cedar_family_clinic"})
    assert r.ok and r.records[0]["health_score"] == 64
    assert r.stale and "warning" in r.for_model()


def test_documents_owner_profile(ctx) -> None:
    docs = call(
        ctx, "search_documents", {"client": "bluefield_imaging", "words": "statement of work scope"}
    )
    assert docs.records and docs.records[0]["url"].startswith("https://example.sharepoint.com")
    owner = call(ctx, "get_owner", {"client": "bluefield_imaging"})
    assert owner.records[0]["dm_am"].startswith("DM Two")
    prof = call(ctx, "get_client_profile", {"client": "bluefield_imaging"})
    assert "imaging" in prof.records[0]["profile"]


def test_persona_sources_enforced(cfg, db) -> None:
    clock = lambda: ANCHOR  # noqa: E731
    ctx = ToolContext(
        cfg=cfg,
        gateway=Gateway(cfg, db, clock=clock),
        sources=Sources(cfg, clock=clock, run_mode="fixture"),
        actor="ba.one@fixture.local",
    )
    assert (
        "not available to your persona"
        in call(ctx, "get_tasks", {"client": "northwind_ortho"}).error
    )
    assert call(ctx, "get_metrics", {"client": "northwind_ortho", "metric": "backlog"}).ok
    assert call(ctx, "get_owner", {"client": "northwind_ortho"}).ok


def test_denials_tell_the_story(ctx) -> None:
    r = call(
        ctx,
        "get_denials",
        {
            "client": "Northwind Orthopedics",
            "period": "last_14_days",
            "group_by": "payer_and_reason",
        },
    )
    assert r.ok and r.records[0]["denials"] > 0 and r.records[0]["denial_rate_pct"] > 0
    assert r.records[1]["group"].startswith("Payer B") and "CO-197" in r.records[1]["group"]
    assert (
        "group_by"
        in call(ctx, "get_denials", {"client": "northwind_ortho", "group_by": "colour"}).error
    )


def test_ar_team_history_activity(ctx) -> None:
    ar = call(ctx, "get_ar_aging", {"client": "northwind_ortho", "weeks": 8})
    assert len(ar.records) == 8 and ar.records[-1]["over_90_pct"] > ar.records[0]["over_90_pct"]
    team = call(ctx, "get_team", {"client": "northwind_ortho"})
    assert any(m["on_leave_today"] for m in team.records)
    hist = call(ctx, "get_task_history", {"client": "northwind_ortho", "task_id": "T-1001"})
    assert {h["change"] for h in hist.records} >= {"created", "due date moved", "assignee"}
    act = call(ctx, "get_client_activity", {"client": "northwind_ortho"})
    assert any("recovery plan" in a["summary"] for a in act.records)
    assert act.records[0]["owner"] in {"CSM One", "DM One"}


def test_my_alerts(ctx) -> None:
    from athena.core import scheduler

    assert call(ctx, "get_my_alerts", {}).records == []
    app_like = type("A", (), {})()
    app_like.cfg, app_like.db, app_like.gateway, app_like.sources = (
        ctx.cfg,
        ctx.gateway.db,
        ctx.gateway,
        ctx.sources,
    )
    app_like.clock, app_like.model = ctx.gateway.clock, None
    scheduler.run_rule(app_like, ctx.cfg.rules["R2"])
    mine = call(ctx, "get_my_alerts", {}).records
    assert mine and {m["client"] for m in mine} <= {"Northwind Orthopedics", "Bluefield Imaging"}
    assert mine[0]["severity"] == "late"
