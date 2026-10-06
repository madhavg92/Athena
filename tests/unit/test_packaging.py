import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _names(reqs: list[str]) -> set[str]:
    return {
        re.split(r"[<>=\[ ]", r.strip(), maxsplit=1)[0].lower()
        for r in reqs
        if r.strip() and not r.startswith("#")
    }


def test_requirements_cover_pyproject() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    wanted = _names(
        project["dependencies"]
        + project["optional-dependencies"]["teams"]
        + project["optional-dependencies"]["postgres"]
    )
    have = _names((ROOT / "requirements.txt").read_text().splitlines())
    assert wanted <= have, wanted - have


def test_function_files() -> None:
    assert json.loads((ROOT / "host.json").read_text())["version"] == "2.0"
    settings = json.loads((ROOT / "local.settings.example.json").read_text())["Values"]
    assert not any(v for k, v in settings.items() if "SECRET" in k)
    assert ".env" in (ROOT / ".funcignore").read_text().split()


def test_runbook_sections() -> None:
    text = (ROOT / "docs/RUNBOOK.md").read_text()
    for heading in (
        "Local test",
        "Azure resources",
        "App settings",
        "Deploy",
        "Rollback",
        "Kill switches",
    ):
        assert heading in text
