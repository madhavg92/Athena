from typer.testing import CliRunner

from athena import demo as d
from athena.cli import app as cli


def test_demo_story(cfg) -> None:
    result = d.run(cfg)
    kinds = {(e.persona, e.kind) for e in result.events}
    assert {("dm_am", "alert"), ("dm_am", "reminder"), ("dm_am", "answer")} <= kinds
    assert {("hub_leader", "digest"), ("hub_leader", "escalation")} <= kinds
    assert {("csm", "answer"), ("csm", "alert"), ("ba", "draft")} <= kinds
    refused = [e for e in result.events if e.question and "not in your scope" in e.text]
    assert len(refused) == 2
    # one consistent day: the same task has the same due time in every message
    t1001 = [
        e.text for e in result.events if "Post payments batch" in e.text and e.kind != "answer"
    ]
    assert t1001 and len({t.split("is due ")[1][:12] for t in t1001}) == 1


def test_demo_cli_and_json(tmp_path) -> None:
    out = CliRunner().invoke(
        cli, ["demo", "--persona", "csm", "--json", str(tmp_path / "demo.json")]
    )
    assert out.exit_code == 0, out.output
    assert "CSM  (csm.one@fixture.local)" in out.output and "DM/AM" not in out.output
    assert (tmp_path / "demo.json").exists()
    assert CliRunner().invoke(cli, ["demo", "--persona", "ceo"]).exit_code == 2
