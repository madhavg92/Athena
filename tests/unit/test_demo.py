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
        e.text
        for e in result.events
        if "Post payments batch (Northwind" in e.text and e.kind != "answer"
    ]
    assert t1001 and len({t.split("is due ")[1][:12] for t in t1001}) == 1


def test_demo_cli_and_json(tmp_path) -> None:
    out = CliRunner().invoke(
        cli, ["demo", "--persona", "csm", "--json", str(tmp_path / "demo.json")]
    )
    assert out.exit_code == 0, out.output
    assert "CSM  (csm.one@fixture.local)" in out.output and "DM/AM  (" not in out.output
    assert (tmp_path / "demo.json").exists()
    assert CliRunner().invoke(cli, ["demo", "--persona", "ceo"]).exit_code == 2


def test_interactive_page_build(cfg, tmp_path) -> None:
    from athena.core import phi

    data = d.interactive_data(cfg)
    assert (
        data["tasks"] and data["metric_rows"] and set(data["clients"]) == set(cfg.owner_map.clients)
    )
    assert all(
        not phi.lint(t["title"], ["fixture.local"]) for t in data["tasks"]
    )  # scrubbed by the connectors
    canned = d.canned_answers(cfg)
    assert set(canned) == set(d.SUGGESTIONS) and all(
        len(v) == len(d.SUGGESTIONS[k]) for k, v in canned.items()
    )
    page = d.save_html(
        d.run(cfg, ["csm"]), cfg.root / "docs/demo/template.html", tmp_path / "p.html", cfg
    ).read_text()
    for marker in ("/*DEMO_DATA*/", "/*ASK_DATA*/", "/*SUGGESTIONS*/", "/*CANNED*/", "/*HUB*/"):
        assert marker not in page
    assert "</script" not in page.split("const DEMO = ", 1)[1].split("const PEOPLE", 1)[0]


def test_proposals_are_computed_from_data(cfg) -> None:
    props = d.proposals(cfg)
    assert set(props) == set(d.PERSONAS)
    cover = props["dm_am"][0]
    assert cover["action"]["kind"] == "send" and cover["action"]["to"] == "hub_leader"
    assert "Analyst N2" in cover["why"] and "%" in cover["action"]["text"]
    csm = props["csm"][0]
    assert csm["action"]["kind"] == "draft" and "never sends to clients" in csm["offer"]
    for cards in props.values():  # only internal messages or drafts; never a client recipient
        for c in cards:
            assert c["action"]["kind"] in ("send", "draft")
            assert c["action"].get("to") in (None, *d.PERSONAS)


def test_hub_view_is_computed_from_data(cfg) -> None:
    from athena.core import phi

    hub = d.hub_view(cfg)
    m = hub["money"]
    assert m["total"] == sum(r["amount_usd"] for r in hub["risks"]) and m["expected"] < m["total"]
    assert m["rows"] == sorted(m["rows"], key=lambda r: -r["amount"]) and len(m["rows"]) <= 4
    assert m["today"]["amount"] == sum(r["amount_usd"] for r in hub["risks"] if r["days_left"] <= 2)
    assert m["who"] and m["who"] in m["plan"]["text"] and len(hub["ops"]["decisions"]) == 3
    # only the hub leader's own clients, and no Cedar (other hub)
    assert {r["client"] for r in hub["risks"]} <= {"Northwind Orthopedics", "Bluefield Imaging"}
    assert {r["client"] for r in hub["economics"]} == {"Northwind Orthopedics", "Bluefield Imaging"}
    assert set(hub["canned"]) == set(hub["suggestions"]) == set(d.HUB_SUGGESTIONS)
    assert hub["call"]["ask"] and hub["call"]["owe"]
    texts = [m["plan"]["text"], *hub["canned"].values(), *hub["call"]["say"]]
    assert all(not phi.lint(t, ["fixture.local"]) for t in texts)
