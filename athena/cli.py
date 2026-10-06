"""The `athena` command."""

from __future__ import annotations

import typer

from athena.core.config import ConfigError, load_config

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
