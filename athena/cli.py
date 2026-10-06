"""The `athena` command."""

from __future__ import annotations

import getpass
import os

import typer

from athena.core.config import ConfigError, load_config
from athena.core.db import Database

app = typer.Typer(help="Athena: Anka OS management assistant.", no_args_is_help=True)
rules_app = typer.Typer(help="Rule files.", no_args_is_help=True)
app.add_typer(rules_app, name="rules")
connectors_app = typer.Typer(help="Data source connectors.", no_args_is_help=True)
eval_app = typer.Typer(help="Evaluation harness.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")
app.add_typer(connectors_app, name="connectors")


@app.callback()
def main() -> None:
    """Athena command line."""
    from athena.core import logs

    logs.setup()


def _config():
    try:
        return load_config()
    except ConfigError as exc:
        typer.echo(f"Invalid config:\n{exc}", err=True)
        raise typer.Exit(2) from exc


@rules_app.command("validate")
def rules_validate() -> None:
    """Check every rule, persona and context file."""
    cfg = _config()
    for rule in cfg.rules.values():
        typer.echo(
            f"ok  {rule.id:<4} {rule.name}  ({rule.action}, {rule.mode}, phase {rule.phase})"
        )
    typer.echo(
        f"{len(cfg.rules)} rules, {len(cfg.personas)} personas, "
        f"{len(cfg.owner_map.people)} people, {len(cfg.owner_map.clients)} clients: valid."
    )


def _db() -> Database:
    return Database()


def _operator() -> str:
    return os.environ.get("ATHENA_OPERATOR") or getpass.getuser()


@app.command()
def kill(
    global_: bool = typer.Option(False, "--global", help="Stop all actions."),
    rule: str | None = typer.Option(None, "--rule", help="Stop one rule, e.g. R2."),
    user: str | None = typer.Option(None, "--user", help="Stop all actions for one person."),
    off: bool = typer.Option(False, "--off", help="Turn the switch off again."),
) -> None:
    """Turn a kill switch on (or off with --off). With no target, list active switches."""
    from athena.core.killswitch import active_switches, set_switch

    db = _db()
    targets = [("global", "*")] if global_ else []
    targets += [("rule", rule)] if rule else []
    targets += [("user", user)] if user else []
    if not targets:
        rows = active_switches(db)
        for row in rows:
            typer.echo(
                f"ON  {row.scope:<6} {row.key}  (by {row.set_by}, {row.set_at:%Y-%m-%d %H:%M} UTC)"
            )
        if not rows:
            typer.echo("No kill switches are on.")
        return
    for scope, key in targets:
        set_switch(db, scope, key, on=not off, set_by=_operator())
        typer.echo(f"{'OFF' if off else 'ON '} {scope} {key}")


@app.command()
def whoami(as_: str = typer.Option(..., "--as", help="Email of the person.")) -> None:
    """Show the name, persona and clients in scope for a person."""
    cfg = _config()
    person = cfg.person(as_)
    if person is None:
        typer.echo("You are not set up for Athena yet.")
        raise typer.Exit(1)
    persona = cfg.personas[person.persona]
    hours, tz = cfg.work_hours_of(as_)
    clients = cfg.scope_of(as_)
    typer.echo(f"Name:     {person.name}")
    typer.echo(f"Email:    {as_.lower()}")
    typer.echo(f"Persona:  {persona.persona}")
    typer.echo(f"Rules:    {', '.join(persona.rules)}")
    typer.echo(
        f"Hours:    {hours.start:%H:%M}-{hours.end:%H:%M} {tz}; digest at {persona.digest_time}"
    )
    typer.echo(
        "Clients:  " + (", ".join(cfg.owner_map.clients[c].name for c in clients) or "(none)")
    )


@connectors_app.command("check")
def connectors_check(
    live: bool = typer.Option(
        False, "--live", help="Check live sources (prints counts and field names only)."
    ),
) -> None:
    """For each source: record count, field names and newest as_of. Never prints record content."""
    from athena.connectors.base import NotConfigured
    from athena.connectors.registry import CONNECTORS, Sources

    cfg = _config()
    sources = Sources(cfg, run_mode="live" if live else "fixture")
    typer.echo(f"Mode: {'live' if live else 'fixture'}")
    for name, cls in CONNECTORS.items():
        for dataset in cls.DATASETS:
            label = f"{name}.{dataset}"
            try:
                rows = sources.read(label)
            except NotConfigured as exc:
                typer.echo(f"{label:<22} not configured: {exc}")
                continue
            except Exception as exc:  # report the type only; messages may hold data
                typer.echo(f"{label:<22} error: {type(exc).__name__}")
                continue
            fields = sorted({k for r in rows for k in r.data})
            newest = max((r.as_of for r in rows), default=None)
            when = f"{newest:%Y-%m-%d %H:%M} UTC" if newest else "-"
            typer.echo(
                f"{label:<22} count={len(rows):<5} newest_as_of={when}  fields={','.join(fields)}"
            )


@eval_app.command("golden")
def eval_golden(
    model: str = typer.Option(
        None, "--model", help="Model name from context/models.yaml (default: the default model)."
    ),
    path: str = typer.Option(
        "tests/golden/golden_questions.yaml", "--file", help="Golden questions file."
    ),
) -> None:
    """Run the golden questions and write reports/eval-<model>-<time>.md."""

    from athena.core.golden import ContractError, run, summary, write_report
    from athena.core.model import ModelError

    cfg = _config()
    name = model or cfg.models.default
    try:
        outcomes = run(cfg, name, cfg.root / path)
    except (ModelError, ContractError) as exc:
        typer.echo(f"Model not available: {exc}", err=True)
        raise typer.Exit(2) from exc
    report = write_report(name, outcomes, cfg.root / "reports")
    s = summary(outcomes)
    for o in outcomes:
        if not o.passed:
            typer.echo(f"FAIL {o.golden.id}: {'; '.join(o.failures)}")
    typer.echo(
        f"{name}: {s['passed']}/{s['questions']} passed, tool accuracy {s['tool_accuracy']:.0%}. Report: {report}"
    )
    if s["passed"] != s["questions"]:
        raise typer.Exit(1)


@app.command()
def ask(
    question: str = typer.Argument(..., help="The question."),
    as_: str = typer.Option(..., "--as", help="Email of the person who asks."),
    model: str = typer.Option(None, "--model", help="Model name from context/models.yaml."),
    conversation: str = typer.Option(
        None, "--conversation", help="Conversation ID (default: the email)."
    ),
) -> None:
    """Ask Athena a question as a person (R1, or R4 for 'brief me on ...')."""
    from athena.app import build
    from athena.core.model import ModelError

    cfg = _config()
    try:
        result = build(cfg=cfg, model=model).asker.ask(question, as_, conversation_id=conversation)
    except ModelError as exc:
        typer.echo(f"Model not available: {exc}", err=True)
        raise typer.Exit(2) from exc
    typer.echo(result.text)
    typer.echo(
        f"\n[{result.rule_id} | tools: {', '.join(result.tools_used) or '-'} | "
        f"{result.tokens_in}+{result.tokens_out} tokens | {result.latency_ms} ms]",
        err=True,
    )


@eval_app.command("summary")
def eval_summary() -> None:
    """Compare the latest golden eval of each model (from reports/)."""
    from athena.core.golden import compare

    cfg = _config()
    table = compare(cfg.root / "reports")
    (cfg.root / "reports").mkdir(exist_ok=True)
    (cfg.root / "reports" / "eval-summary.md").write_text("# Model bake-off\n\n" + table)
    typer.echo(table)


db_app = typer.Typer(help="Database.", no_args_is_help=True)
app.add_typer(db_app, name="db")


@db_app.command("upgrade")
def db_upgrade(
    sql: bool = typer.Option(False, "--sql", help="Print the SQL instead of running it."),
) -> None:
    """Apply Alembic migrations to DATABASE_URL (Postgres in production)."""
    from alembic import command
    from alembic.config import Config

    cfg = _config()
    command.upgrade(Config(str(cfg.root / "alembic.ini")), "head", sql=sql)


@app.command()
def tick(
    rule: list[str] = typer.Option(None, "--rule", help="Run these rules now, even if not due."),
) -> None:
    """Run due rules once (fixture mode unless ATHENA_MODE=live), release held messages, send due digests."""
    from athena.app import build
    from athena.core import scheduler

    out = scheduler.tick(build(cfg=_config()), force=rule or None)
    for r in out["runs"]:
        if r["stale"] or not r["ran"]:
            typer.echo(f"{r['rule_id']}: not run ({r['reason']})")
        else:
            msgs = ", ".join(f"{k} {v}" for k, v in r["messages"].items()) or "none"
            typer.echo(
                f"{r['rule_id']}: {r['hits']} hits, {r['opened']} opened, {r['closed']} closed; messages: {msgs}"
            )
    if not out["runs"]:
        typer.echo("No rules due.")
    typer.echo(f"Held messages released: {out['released']}. Digests sent: {out['digests']}.")


@app.command()
def review(
    alert: int = typer.Option(None, "--alert", help="Alert ID to mark."),
    verdict: str = typer.Option(None, "--verdict", help="correct or wrong."),
    note: str = typer.Option(None, "--note", help="Optional note."),
    as_: str = typer.Option(None, "--as", help="Reviewer email (an owner of the client)."),
    rule: str = typer.Option(None, "--rule", help="Only this rule."),
    all_: bool = typer.Option(False, "--all", help="Include alerts already marked."),
) -> None:
    """List shadow alerts, or mark one correct or wrong."""
    from sqlalchemy import select

    from athena.app import build
    from athena.core import review as rv
    from athena.core.db import Receipt

    app_ = build(cfg=_config())
    if alert is not None:
        if not (verdict and as_):
            typer.echo("Give --verdict correct|wrong and --as <email>.", err=True)
            raise typer.Exit(2)
        error = rv.mark(app_, alert, as_, verdict, note)
        if error:
            typer.echo(f"Not recorded: {error}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Alert {alert} marked {verdict}.")
        return
    rows = rv.pending(app_, rule, include_marked=all_)
    if not rows:
        typer.echo("No shadow alerts to review.")
        return
    with app_.db.session() as s:
        for a in rows:
            text = s.scalars(
                select(Receipt.output).where(
                    Receipt.item_key == a.item_key, Receipt.status == "shadow"
                )
            ).first()
            typer.echo(
                f"#{a.id:<5} {a.rule_id} {a.severity:<10} {a.client:<20} {a.state:<6} {text}"
            )
    typer.echo(
        f"\n{len(rows)} alerts. Mark one: athena review --alert <id> --verdict correct|wrong --as <email>"
    )


@app.command()
def backtest(
    rule: str = typer.Argument(..., help="Rule ID, e.g. R2."),
    days: int = typer.Option(30, "--days", help="Days of history to replay."),
) -> None:
    """Replay history through a rule: alerts opened, messages per person per day, wrong alerts."""
    from athena.core.backtest import run

    cfg = _config()
    if rule not in cfg.rules:
        typer.echo(f"Unknown rule {rule}.", err=True)
        raise typer.Exit(2)
    try:
        report = run(cfg, rule, days)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(report.text())


@app.command()
def stats(days: int = typer.Option(7, "--days", help="Look back this many days.")) -> None:
    """Measurements: alerts, messages, wrong marks, time to close, questions, cost per rule and user."""
    from athena.app import build
    from athena.core.stats import collect

    data = collect(build(cfg=_config()), days)
    typer.echo(f"Last {data['days']} days\n\nRules:")
    for rule_id, r in data["rules"].items():
        typer.echo(f"  {rule_id}: " + ", ".join(f"{k} {v}" for k, v in r.items() if v is not None))
    if not data["rules"]:
        typer.echo("  (no alerts or messages)")
    typer.echo("\nQuestions: " + ", ".join(f"{k} {v}" for k, v in data["questions"].items()))
    typer.echo(
        "Cost by rule (USD): "
        + (", ".join(f"{k} {v}" for k, v in data["cost_usd_by_rule"].items()) or "-")
    )
    typer.echo(
        "Tokens by rule: "
        + (", ".join(f"{k} {v}" for k, v in data["tokens_by_rule"].items()) or "-")
    )
    typer.echo(
        "Cost by user (USD): "
        + (", ".join(f"{k} {v}" for k, v in data["cost_usd_by_user"].items()) or "-")
    )
    typer.echo("Not measured yet: " + "; ".join(data["not_measured"]))


@app.command()
def demo(
    persona: list[str] = typer.Option(
        None, "--persona", help="dm_am, hub_leader, csm, ba (default: all)."
    ),
    alerts: int = typer.Option(3, "--alerts", help="Alerts to show for each persona and kind."),
    json_out: str = typer.Option(None, "--json", help="Also write the demo as JSON to this path."),
    html_out: str = typer.Option(None, "--html", help="Also write the demo web page to this path."),
) -> None:
    """A synthetic Monday at Anka, persona by persona. Uses fixture data and an in-memory database."""
    from pathlib import Path

    from athena import demo as d

    cfg = _config()
    unknown = set(persona or []) - set(d.PERSONAS)
    if unknown:
        typer.echo(
            f"Unknown persona(s): {', '.join(sorted(unknown))}. Use: {', '.join(d.PERSONAS)}",
            err=True,
        )
        raise typer.Exit(2)
    result = d.run(cfg, persona or None)
    typer.echo(d.as_text(result, alerts))
    if json_out:
        typer.echo(f"JSON: {d.save_json(result, Path(json_out))}")
    if html_out:
        page = d.save_html(
            result, cfg.root / "docs" / "demo" / "template.html", Path(html_out), cfg
        )
        typer.echo(f"Page: {page}")
