"""The `athena` command."""

import typer

app = typer.Typer(help="Athena: Anka OS management assistant.", no_args_is_help=True)


@app.callback()
def main() -> None:
    """Athena command line."""
