import json
from types import SimpleNamespace

import pytest

from athena.core.golden import ContractError, compare, run, summary, write_report
from athena.core.model import OpenAICompatModel
from tests.unit.test_golden import GOLDEN


class EchoCompletions:
    """A fake OpenAI-compatible endpoint that never calls tools: everything is 'I do not know'."""

    def create(self, **kwargs):
        msg = SimpleNamespace(content="I do not know.", tool_calls=None)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg)],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=5),
        )


def test_any_model_runs_through_harness(cfg, tmp_path) -> None:
    spec = cfg.models.models["candidate_a"]
    model = OpenAICompatModel(
        "candidate_a",
        spec,
        client=SimpleNamespace(chat=SimpleNamespace(completions=EchoCompletions())),
    )
    outcomes = run(cfg, "candidate_a", GOLDEN, model=model)
    s = summary(outcomes)
    assert 0 < s["passed"] < s["questions"]  # idk questions pass, others fail
    assert s["tokens_in"] == 100 * s["questions"]
    write_report("candidate_a", outcomes, tmp_path)
    write_report("stub", run(cfg, "stub", GOLDEN), tmp_path)
    table = compare(tmp_path)
    rows = [
        ln for ln in table.splitlines() if ln.startswith("| stub") or ln.startswith("| candidate_a")
    ]
    assert rows[0].startswith("| stub") and "100%" in rows[0]
    assert json.loads(next(tmp_path.glob("eval-candidate_a-*.json")).read_text())["failed"]


def test_live_needs_contract(cfg, monkeypatch) -> None:
    monkeypatch.setenv("ATHENA_MODE", "live")
    with pytest.raises(ContractError, match="G5"):
        run(cfg, "candidate_a", GOLDEN)
