from sqlalchemy import select

from athena.core.db import Receipt


def test_brief_sections_in_order(app) -> None:
    r = app.asker.ask("Brief me on Northwind Orthopedics", "csm.one@fixture.local")
    assert r.rule_id == "R4"
    heads = [ln for ln in r.answer.splitlines() if ln.startswith("**")]
    assert heads == [
        "**Health and open tickets**",
        "**Metrics**",
        "**Open tasks**",
        "**Recent documents**",
        "**Profile**",
    ]
    assert "Health score for Northwind Orthopedics is 72" in r.answer
    assert {
        "get_tickets",
        "get_metrics",
        "get_tasks",
        "search_documents",
        "get_client_profile",
    } <= set(r.tools_used)
    names = {s.name for s in r.sources}
    assert {
        "cs_hub.tickets",
        "cs_hub.health",
        "supaboard.metrics",
        "smartsheet.tasks",
        "sharepoint.documents",
        "client_profile",
    } <= names
    with app.db.session() as s:
        assert s.scalars(select(Receipt)).one().rule_id == "R4"


def test_brief_system_prompt_lists_sections(app) -> None:
    text = app.asker._system("csm.one@fixture.local", "R4", "brief me on Northwind")
    assert "health, open tickets, metrics, open tasks, recent documents" in text
    assert "backlog:" in text  # metric definitions included for briefs


def test_brief_not_in_persona_falls_back_to_r1(app) -> None:
    r = app.asker.ask("Brief me on Northwind Orthopedics", "hl.key@fixture.local")
    assert r.rule_id == "R1"
