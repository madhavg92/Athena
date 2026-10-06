from typer.testing import CliRunner

from athena.cli import app


def test_check_fixture() -> None:
    result = CliRunner().invoke(app, ["connectors", "check"])
    assert result.exit_code == 0, result.output
    assert "smartsheet.tasks       count=30" in result.output
    assert "supaboard.metrics" in result.output and "entra.users" in result.output
    # no record content
    assert "Post payments" not in result.output and "Northwind" not in result.output


def test_check_live_without_settings(monkeypatch) -> None:
    for var in ("SMARTSHEET_TOKEN", "SUPABOARD_BASE_URL", "CSHUB_BASE_URL", "GRAPH_TENANT_ID"):
        monkeypatch.delenv(var, raising=False)
    result = CliRunner().invoke(app, ["connectors", "check", "--live"])
    assert result.exit_code == 0, result.output
    from athena.connectors.registry import CONNECTORS

    assert result.output.count("not configured") == sum(
        len(c.DATASETS) for c in CONNECTORS.values()
    )
