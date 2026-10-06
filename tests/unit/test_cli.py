from typer.testing import CliRunner

from athena.cli import app


def test_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Athena" in result.output
