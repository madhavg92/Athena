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
    assert r.answer.startswith("backlog for Northwind Orthopedics is")
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
