from sqlalchemy import select

from athena.core.ask import Asker, pick_rule
from athena.core.db import QuestionLog, Receipt, Turn
from athena.core.killswitch import set_switch
from athena.core.model import ModelReply, StubModel, ToolCall

DM = "dm.one@fixture.local"
HL = "hl.key@fixture.local"


def test_pick_rule() -> None:
    assert pick_rule("Brief me on Northwind") == "R4"
    assert pick_rule("brief Northwind") == "R4"
    assert pick_rule("Who is brief?") == "R1"


def test_answer_with_sources_footer(app) -> None:
    r = app.asker.ask("What is the backlog for Northwind Orthopedics?", DM)
    assert r.answer.startswith("Backlog for Northwind Orthopedics is")
    assert r.footer.startswith("Sources:\n- supaboard.metrics, as of")
    assert r.tools_used == ["get_metrics"] and not r.idk and r.status == "sent"
    with app.db.session() as s:
        log = s.scalars(select(QuestionLog)).one()
        receipt = s.scalars(select(Receipt)).one()
    assert (
        log.tools == ["get_metrics"]
        and receipt.action_type == "answer"
        and receipt.status == "sent"
    )


def test_idk_when_nothing_matches(app) -> None:
    r = app.asker.ask("What is the meaning of life?", DM)
    assert r.idk and r.footer == ""


def test_out_of_scope_refused(app) -> None:
    r = app.asker.ask("Show late tasks for Cedar Family Clinic", DM)
    assert r.refused and "not in your scope" in r.answer and r.footer == ""


def test_stale_data_flagged(app) -> None:
    r = app.asker.ask("What is the health score for Cedar Family Clinic?", "hl.small@fixture.local")
    assert r.stale and r.answer.startswith("Data is not current")


def test_unknown_user_and_kill_switch(app) -> None:
    assert "not set up" in app.asker.ask("backlog Northwind", "x@fixture.local").answer
    set_switch(app.db, "user", DM, True, "ops")
    assert app.asker.ask("backlog Northwind", DM).answer.startswith("Athena is paused")


def test_model_facts_without_data_replaced(app) -> None:
    model = StubModel(script=[ModelReply(text="Backlog is 12 and all on target.")])
    r = Asker(app.cfg, app.db, app.gateway, app.sources, model).ask("backlog Northwind", DM)
    assert r.idk and r.answer.startswith("I do not know. I checked:")


def test_tool_call_limit(app) -> None:
    many = [
        ToolCall(id=str(i), name="get_owner", arguments={"client": "northwind_ortho"})
        for i in range(10)
    ]
    model = StubModel(script=[ModelReply(tool_calls=many), ModelReply(text="Owner list.")])
    r = Asker(app.cfg, app.db, app.gateway, app.sources, model).ask("owners Northwind", DM)
    assert len(r.tools_used) == 8 and r.answer == "Owner list."


def test_last_six_turns_sent_to_model(app) -> None:
    seen = []

    class Spy(StubModel):
        def chat(self, messages, tools):
            seen.append(list(messages))
            return super().chat(messages, tools)

    asker = Asker(
        app.cfg,
        app.db,
        app.gateway,
        app.sources,
        Spy(clients={"Northwind Orthopedics": "northwind_ortho"}),
    )
    for i in range(5):
        asker.ask(f"backlog Northwind {i}", DM)
    first_call = seen[-2]  # last question: plan call
    history = [m for m in first_call[1:-1]]
    assert len(history) == 6 and history[-1]["role"] == "assistant"
    with app.db.session() as s:
        assert len(s.scalars(select(Turn)).all()) == 10


def test_phi_in_answer_blocked(app) -> None:
    model = StubModel(
        script=[
            ModelReply(
                tool_calls=[
                    ToolCall(id="1", name="get_owner", arguments={"client": "northwind_ortho"})
                ]
            ),
            ModelReply(text="Patient John Smith SSN 123-45-6789"),
        ]
    )
    r = Asker(app.cfg, app.db, app.gateway, app.sources, model).ask("owners Northwind", DM)
    assert r.status == "refused" and "safety check" in r.answer and "6789" not in r.answer


def test_cross_client_questions_without_a_client_name(app) -> None:
    money = app.asker.ask("Where is money at risk?", HL)
    assert money.tools_used == ["get_money_at_risk"] and not money.idk
    assert money.answer.startswith("$") and "at risk in the next 14 days" in money.answer
    assert "supaboard.denied_claims" in money.footer
    margin = app.asker.ask("Which client has the lowest margin per FTE?", HL)
    assert margin.tools_used == ["get_client_economics"] and "per FTE" in margin.answer
    assert "Cedar" not in margin.answer  # another hub
    week = app.asker.ask("What meetings do I have this week?", HL)
    assert week.tools_used == ["get_meetings"] and "Northwind weekly call" in week.answer
    assert app.asker.ask("What is the meaning of life?", HL).idk


def test_hub_ops_questions(app) -> None:
    lst = app.asker.ask("What is outstanding today?", HL)
    assert lst.tools_used == ["get_standing_list"] and "Waiting on the client: 4" in lst.answer
    cover = app.asker.ask("Who can cover today?", HL)
    assert cover.tools_used == ["get_capacity"] and "Analyst B1" in cover.answer
    blocked = app.asker.ask("What is blocked at Northwind?", HL)
    assert blocked.tools_used == ["get_blocked_work"] and "BL-301" in blocked.answer
    audit = app.asker.ask("Which audit findings are open?", HL)
    assert audit.tools_used == ["get_quality"] and "QF-41" in audit.answer
