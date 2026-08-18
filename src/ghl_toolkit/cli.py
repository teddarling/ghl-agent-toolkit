"""Typer CLI entry point for the ghl command."""

import importlib.metadata

import typer

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Inspect GoHighLevel data and run gated agents against it."""


@app.command()
def version() -> None:
    """Print the installed ghl-toolkit version."""
    typer.echo(importlib.metadata.version("ghl-toolkit"))
