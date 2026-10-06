from typer.testing import CliRunner

from athena.cli import app
from athena.core.db import Database
from athena.core.killswitch import blocked_by, set_switch


def test_no_switches(db: Database) -> None:
    assert blocked_by(db, "R2", ["a@fixture.local"]) is None


def test_global(db: Database) -> None:
    set_switch(db, "global", "", True, "ops")
    assert blocked_by(db, "R2") == "kill switch: global"
    set_switch(db, "global", "", False, "ops")
    assert blocked_by(db, "R2") is None


def test_rule_and_user(db: Database) -> None:
    set_switch(db, "rule", "R2", True, "ops")
    set_switch(db, "user", "DM.One@fixture.local", True, "ops")
    assert blocked_by(db, "R2") == "kill switch: rule R2"
    assert blocked_by(db, "R3") is None
    assert (
        blocked_by(db, "R3", ["dm.one@fixture.local"]) == "kill switch: user dm.one@fixture.local"
    )


def test_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/k.db")
    runner = CliRunner()
    assert runner.invoke(app, ["kill", "--rule", "R2"]).exit_code == 0
    listing = runner.invoke(app, ["kill"])
    assert "rule   R2" in listing.output
    assert runner.invoke(app, ["kill", "--rule", "R2", "--off"]).exit_code == 0
    assert "No kill switches" in runner.invoke(app, ["kill"]).output
    assert blocked_by(Database(f"sqlite:///{tmp_path}/k.db"), "R2") is None
