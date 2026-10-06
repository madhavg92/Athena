from sqlalchemy import select
from typer.testing import CliRunner

from athena.bot.teams import TeamsBot
from athena.cli import app as cli
from athena.core import review, scheduler
from athena.core.db import ReviewMark

DM_ID = "00000000-0000-4000-8000-000000000003"  # dm.one


def shadow_run(app):
    scheduler.run_rule(app, app.cfg.rules["R2"])  # R2 ships in shadow
    return review.pending(app)


def test_shadow_alerts_listed_not_delivered(app) -> None:
    rows = shadow_run(app)
    assert len(rows) == 12
    assert not app.gateway.deliverer.sent


def test_mark_by_owner_only(app) -> None:
    rows = shadow_run(app)
    nw = next(a for a in rows if a.client == "northwind_ortho")
    assert "not an owner" in review.mark(app, nw.id, "dm.two@fixture.local", "wrong")
    assert review.mark(app, nw.id, "dm.one@fixture.local", "maybe").startswith("verdict")
    assert review.mark(app, nw.id, "dm.one@fixture.local", "wrong", "extension agreed") is None
    assert nw.id not in {a.id for a in review.pending(app)}
    assert nw.id in {a.id for a in review.pending(app, include_marked=True)}


def test_teams_buttons(app) -> None:
    rows = shadow_run(app)
    nw = next(a for a in rows if a.client == "northwind_ortho")
    reply = TeamsBot(app).handle_card_action(
        {"athena": "review", "alert_id": nw.id, "verdict": "correct"}, DM_ID, None
    )
    assert reply.text.startswith("Thanks")
    with app.db.session() as s:
        assert s.scalars(select(ReviewMark)).one().verdict == "correct"


def test_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/r.db")
    runner = CliRunner()
    assert "No shadow alerts" in runner.invoke(cli, ["review"]).output
    runner.invoke(cli, ["tick", "--rule", "R2"])
    listing = runner.invoke(cli, ["review"]).output
    assert "12 alerts" in listing
    first = listing.split()[0].lstrip("#")
    out = runner.invoke(
        cli, ["review", "--alert", first, "--verdict", "correct", "--as", "hl.key@fixture.local"]
    )
    assert "Not recorded" in out.output or "marked correct" in out.output
