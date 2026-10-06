from typer.testing import CliRunner

from athena.cli import app


def test_ask_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/a.db")
    result = CliRunner().invoke(
        app,
        ["ask", "What is the backlog for Northwind Orthopedics?", "--as", "csm.one@fixture.local"],
    )
    assert result.exit_code == 0, result.output
    assert "backlog for Northwind Orthopedics is" in result.output and "Sources:" in result.output


def test_ask_cli_unknown_user(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/a.db")
    result = CliRunner().invoke(app, ["ask", "hi", "--as", "x@fixture.local"])
    assert "not set up for Athena" in result.output
