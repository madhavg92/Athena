from typer.testing import CliRunner

from athena.cli import app as cli
from athena.core.backtest import run


def test_backtest_r2(cfg) -> None:
    report = run(cfg, "R2", days=7)
    assert report.alerts_opened > 0 and report.messages > 0
    assert set(report.by_severity) <= {"late", "at_risk"}
    assert any(p.startswith("dm.") for p in report.per_person_per_day)
    assert all(v <= 40 for v in report.max_per_person_day.values())
    assert report.wrong_rate is None or 0 <= report.wrong_rate <= 1


def test_backtest_is_deterministic(cfg) -> None:
    assert run(cfg, "R2", days=3).model_dump() == run(cfg, "R2", days=3).model_dump()


def test_backtest_refuses_non_check_rules(cfg) -> None:
    import pytest

    with pytest.raises(ValueError):
        run(cfg, "R1", days=1)
    with pytest.raises(ValueError, match="no history"):
        run(cfg, "R3", days=1)


def test_cli() -> None:
    result = CliRunner().invoke(cli, ["backtest", "R2", "--days", "2"])
    assert result.exit_code == 0, result.output
    assert "Backtest R2" in result.output and "Messages per person per day" in result.output
