from typer.testing import CliRunner

from athena.cli import app


def test_whoami_dm() -> None:
    result = CliRunner().invoke(app, ["whoami", "--as", "dm.one@fixture.local"])
    assert result.exit_code == 0
    assert "DM One" in result.output and "dm_am" in result.output
    assert "Northwind Orthopedics" in result.output
    assert "Bluefield" not in result.output


def test_whoami_hub_leader_two_clients() -> None:
    result = CliRunner().invoke(app, ["whoami", "--as", "HL.Key@fixture.local"])
    assert "Northwind Orthopedics, Bluefield Imaging" in result.output


def test_whoami_unknown() -> None:
    result = CliRunner().invoke(app, ["whoami", "--as", "stranger@fixture.local"])
    assert result.exit_code == 1
    assert "not set up for Athena" in result.output
