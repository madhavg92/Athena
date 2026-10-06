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


@app.callback()
def main() -> None:
    """Athena command line."""


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
