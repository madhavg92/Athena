from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from athena.cli import app
from athena.core.config import ConfigError, WorkHours, load_config
from athena.core.durations import parse_duration


def test_seed_files_load() -> None:
    cfg = load_config()
    assert set(cfg.rules) == {"R1", "R2", "R3", "R4", "R5", "R6"}
    assert set(cfg.personas) == {"hub_leader", "dm_am", "csm", "ba", "cs_lead"}
    assert cfg.rules["R2"].data_max_age == timedelta(minutes=30)
    assert cfg.rules["R2"].ladder[1].after == timedelta(hours=4)
    assert cfg.rules["R1"].is_question


def test_scope() -> None:
    cfg = load_config()
    assert cfg.scope_of("dm.one@fixture.local") == ["northwind_ortho"]
    assert cfg.scope_of("hl.key@fixture.local") == ["northwind_ortho", "bluefield_imaging"]
    assert cfg.scope_of("nobody@fixture.local") == []


@pytest.mark.parametrize(
    "text,expected",
    [("30m", timedelta(minutes=30)), ("4h", timedelta(hours=4)), ("1d", timedelta(days=1))],
)
def test_durations(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


def test_bad_duration() -> None:
    with pytest.raises(ValueError):
        parse_duration("4 hours")


def test_work_hours_wrap_midnight() -> None:
    from datetime import time

    hours = WorkHours.parse("17:00-02:00")
    assert hours.contains(time(23, 0)) and hours.contains(time(1, 0))
    assert not hours.contains(time(12, 0))


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new))


@pytest.mark.parametrize(
    "rel,old,new,expect",
    [
        ("rules/R2.yaml", "op: ne", "op: not_equal", ["rules/R2.yaml", "op", "unknown op"]),
        ("rules/R2.yaml", "data_max_age: 30m", "data_max_age: soon", ["data_max_age", "duration"]),
        ("rules/R2.yaml", "action: notify", "action: write", ["action", "disabled"]),
        ("rules/R2.yaml", "to: hub_leader", "to: ceo", ["ladder.1.to", "unknown owner-map role"]),
        ("rules/R3.yaml", "30 8 * * 1-5", "99 8 * * *", ["rules/R3.yaml", "cron"]),
        ("personas/csm.yaml", "17:00-02:00", "5pm-2am", ["personas/csm.yaml", "work_hours"]),
        ("rules/R1.yaml", "max_tool_calls: 8", "max_tool_calls: 8\ncolour: red", ["colour"]),
    ],
)
def test_broken_file_names_file_field_reason(
    config_copy: Path, rel: str, old: str, new: str, expect: list[str]
) -> None:
    _edit(config_copy / rel, old, new)
    with pytest.raises(ConfigError) as info:
        load_config(config_copy)
    for part in expect:
        assert part in str(info.value)


def test_rules_validate_cli() -> None:
    result = CliRunner().invoke(app, ["rules", "validate"])
    assert result.exit_code == 0, result.output
    assert "6 rules" in result.output


def test_rules_validate_cli_fails(config_copy: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _edit(config_copy / "rules/R2.yaml", "op: ne", "op: nope")
    monkeypatch.setenv("ATHENA_HOME", str(config_copy))
    result = CliRunner().invoke(app, ["rules", "validate"])
    assert result.exit_code == 2
    assert "rules/R2.yaml" in result.output
