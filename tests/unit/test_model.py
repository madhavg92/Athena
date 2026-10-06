import json
from types import SimpleNamespace

import pytest

from athena.core.config import ModelSpec
from athena.core.model import (
    ModelError,
    ModelReply,
    OpenAICompatModel,
    StubModel,
    ToolCall,
    cost_usd,
    get_model,
)

CLIENTS = {"Northwind Orthopedics": "northwind_ortho", "Bluefield Imaging": "bluefield_imaging"}
TOOLS = [
    {"type": "function", "function": {"name": n}}
    for n in (
        "get_tasks",
        "get_metrics",
        "get_tickets",
        "search_documents",
        "get_owner",
        "get_client_profile",
    )
]


def msgs(q: str, *tool_msgs: dict) -> list[dict]:
    return [{"role": "system", "content": "rules"}, {"role": "user", "content": q}, *tool_msgs]


def test_stub_routes_metric_and_tasks() -> None:
    reply = StubModel(CLIENTS).chat(
        msgs("What is the backlog and late tasks for Northwind Orthopedics?"), TOOLS
    )
    names = [c.name for c in reply.tool_calls]
    assert names == ["get_metrics", "get_tasks"]
    assert reply.tool_calls[0].arguments == {
        "client": "Northwind Orthopedics",
        "metric": "backlog",
        "period": "latest",
    }
    assert reply.tokens_in > 0


def test_stub_idk_without_client() -> None:
    reply = StubModel(CLIENTS).chat(msgs("What is the weather?"), TOOLS)
    assert not reply.tool_calls and reply.text.startswith("I do not know")


def test_stub_brief_calls_sections() -> None:
    reply = StubModel(CLIENTS).chat(msgs("Brief me on Bluefield Imaging"), TOOLS)
    assert {c.name for c in reply.tool_calls} == {
        "get_tickets",
        "get_metrics",
        "get_tasks",
        "search_documents",
        "get_client_profile",
    }


def test_stub_answers_from_results() -> None:
    result = {
        "ok": True,
        "client_name": "Northwind Orthopedics",
        "metric": "backlog",
        "records": [{"date": "2026-10-04", "actual": 412.0, "target": 300.0}],
        "as_of": ["x"],
    }
    reply = StubModel(CLIENTS).chat(
        msgs(
            "backlog Northwind",
            {"role": "tool", "name": "get_metrics", "content": json.dumps(result)},
        ),
        TOOLS,
    )
    assert reply.text == "backlog for Northwind Orthopedics is 412.0 (target 300.0) on 2026-10-04."


def test_stub_scope_refusal_and_stale() -> None:
    refused = {"ok": False, "error": "refused: x is not in your scope"}
    r = StubModel(CLIENTS).chat(
        msgs("q", {"role": "tool", "name": "get_tasks", "content": json.dumps(refused)}), TOOLS
    )
    assert "not in your scope" in r.text
    stale = {
        "ok": True,
        "client_name": "C",
        "records": [{"health_score": 1, "trend": "down"}],
        "warning": "w",
        "as_of": ["cs_hub.health: 2026-10-02 03:00 UTC"],
    }
    r = StubModel(CLIENTS).chat(
        msgs("q", {"role": "tool", "name": "get_tickets", "content": json.dumps(stale)}), TOOLS
    )
    assert r.text.startswith("Data is not current (cs_hub.health: 2026-10-02 03:00 UTC)")


def test_stub_script() -> None:
    stub = StubModel(
        script=[
            ModelReply(tool_calls=[ToolCall(id="1", name="get_owner", arguments={})]),
            ModelReply(text="done"),
        ]
    )
    assert stub.chat(msgs("q"), TOOLS).tool_calls[0].name == "get_owner"
    assert stub.chat(msgs("q"), TOOLS).text == "done"


def test_cost() -> None:
    spec = ModelSpec(kind="openai_compatible", price_per_mtok_in=1.0, price_per_mtok_out=2.0)
    assert cost_usd(spec, 1_000_000, 500_000) == 2.0


class FakeCompletions:
    def __init__(self) -> None:
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        tc = SimpleNamespace(
            id="c1", function=SimpleNamespace(name="get_tasks", arguments='{"client": "Northwind"}')
        )
        msg = SimpleNamespace(content=None, tool_calls=[tc])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=120, completion_tokens=8),
        )


def test_openai_compat_parses_tool_calls() -> None:
    completions = FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    spec = ModelSpec(kind="openai_compatible", model="m1")
    reply = OpenAICompatModel("a", spec, client=client).chat(msgs("q"), TOOLS)
    assert reply.tool_calls[0].arguments == {"client": "Northwind"} and reply.tokens_in == 120
    assert completions.kwargs["model"] == "m1" and completions.kwargs["tools"] == TOOLS


def test_get_model(cfg, monkeypatch) -> None:
    assert get_model(cfg).name == "stub"
    monkeypatch.delenv("MODEL_A_BASE_URL", raising=False)
    with pytest.raises(ModelError, match="G5"):
        get_model(cfg, "candidate_a")
    with pytest.raises(ModelError, match="unknown model"):
        get_model(cfg, "nope")
