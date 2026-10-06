from datetime import timedelta

from typer.testing import CliRunner

from athena.app import build
from athena.cli import app as cli
from athena.core import review, scheduler
from athena.core.stats import collect


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def test_collect(cfg, db, anchor) -> None:
    clock = Clock(anchor)
    app = build(cfg=cfg, db=db, clock=clock, run_mode="fixture")
    scheduler.run_rule(app, app.cfg.rules["R2"])
    alerts = review.pending(app)
    review.mark(
        app,
        alerts[0].id,
        "hl.key@fixture.local"
        if alerts[0].client != "cedar_family_clinic"
        else "hl.small@fixture.local",
        "wrong",
    )
    app.asker.ask("What is the backlog for Northwind Orthopedics?", "dm.one@fixture.local")
    app.asker.ask("What is the weather?", "dm.one@fixture.local")
    clock.now += timedelta(hours=1)
    data = collect(app, 7)
    r2 = data["rules"]["R2"]
    assert (
        r2["alerts_opened"] == 12
        and r2["messages_shadow"] == 12
        and r2["marked_wrong"] == 1
        and r2["wrong_rate"] == 1.0
    )
    assert data["questions"]["asked"] == 2 and data["questions"]["i_do_not_know"] == 1
    assert data["tokens_by_rule"]["R1"] > 0


def test_cli(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/s.db")
    out = CliRunner().invoke(cli, ["stats"])
    assert out.exit_code == 0 and "no alerts or messages" in out.output
