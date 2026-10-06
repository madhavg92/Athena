from pathlib import Path

from typer.testing import CliRunner

from athena.cli import app
from athena.core.golden import load_golden, run, summary, write_report

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "tests/golden/golden_questions.yaml"


def test_golden_set_shape() -> None:
    items = load_golden(GOLDEN)
    assert len(items) >= 20
    assert {g.persona for g in items} == {"hub_leader", "dm_am", "csm", "ba"}
    assert (
        any(g.expect.refused for g in items)
        and any(g.expect.idk for g in items)
        and any(g.expect.stale for g in items)
    )
    assert len({g.id for g in items}) == len(items)


def test_stub_passes_all(cfg, tmp_path) -> None:
    outcomes = run(cfg, "stub", GOLDEN)
    failed = {o.golden.id: o.failures for o in outcomes if not o.passed}
    assert not failed
    s = summary(outcomes)
    assert s["pass_rate"] == 1.0 and s["tool_accuracy"] == 1.0
    report = write_report("stub", outcomes, tmp_path)
    assert "| Pass rate | 24/24 (100%) |" in report.read_text()


def test_cli(monkeypatch, tmp_path) -> None:
    result = CliRunner().invoke(app, ["eval", "golden", "--model", "stub"])
    assert result.exit_code == 0, result.output
    assert "24/24 passed" in result.output
