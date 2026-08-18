"""Typer CLI entry point for the ghl command."""

import importlib.metadata

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from ghl_toolkit.client import ApiError, AuthError, GHLClient, NotFound
from ghl_toolkit.settings import get_settings

app = typer.Typer(no_args_is_help=True)
console = Console()

RATE_LIMIT_HEADERS = (
    "X-RateLimit-Limit-Daily",
    "X-RateLimit-Daily-Remaining",
    "X-RateLimit-Interval-Milliseconds",
    "X-RateLimit-Max",
    "X-RateLimit-Remaining",
)


@app.callback()
def main() -> None:
    """Inspect GoHighLevel data and run gated agents against it."""


@app.command()
def version() -> None:
    """Print the installed ghl-toolkit version."""
    typer.echo(importlib.metadata.version("ghl-toolkit"))


@app.command()
def doctor() -> None:
    """Verify auth and connectivity against the configured location."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        missing = ", ".join(f"GHL_{str(err['loc'][0]).upper()}" for err in exc.errors())
        console.print(f"[red]✗[/red] Configuration incomplete — missing: {missing}")
        console.print("Copy .env.example to .env and fill in your HighLevel credentials.")
        raise typer.Exit(2) from None

    console.print(f"Checking location {settings.location_id} at {settings.api_base_url} ...")
    try:
        with GHLClient(settings) as client:
            response = client.get(f"/locations/{settings.location_id}")
    except AuthError as exc:
        if exc.status_code == 403:
            console.print(
                "[red]✗[/red] Token lacks the locations.readonly scope (403 Forbidden). "
                "Grant it on the Private Integration and try again."
            )
        else:
            console.print("[red]✗[/red] Token rejected (401 Unauthorized) — check GHL_API_TOKEN.")
        raise typer.Exit(1) from None
    except NotFound:
        console.print("[red]✗[/red] Location not found — check GHL_LOCATION_ID.")
        raise typer.Exit(1) from None
    except ApiError as exc:
        console.print(f"[red]✗[/red] API error {exc.status_code}: {exc.message}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as exc:
        console.print(f"[red]✗[/red] Could not reach {settings.api_base_url}: {exc}")
        raise typer.Exit(1) from None

    # VERIFY: the get-location response schema is not rendered in the official docs; the
    # {"location": {...}} envelope is read defensively. See VERIFY.md (V3).
    body = response.json()
    location = body.get("location", {}) if isinstance(body, dict) else {}
    name = location.get("name") if isinstance(location, dict) else None

    console.print(f"[green]✓[/green] Auth OK — token accepted for location {settings.location_id}")
    console.print(f"[green]✓[/green] Location: {name or '(name not returned)'}")

    limits = [
        (header, response.headers[header])
        for header in RATE_LIMIT_HEADERS
        if header in response.headers
    ]
    if limits:
        table = Table(title="Rate limits")
        table.add_column("Header")
        table.add_column("Value", justify="right")
        for header, value in limits:
            table.add_row(header, value)
        console.print(table)

    console.print(
        "Note: Private Integration token scopes cannot be introspected via any documented "
        "API. This check verifies locations.readonly by probing; other scopes are verified "
        "the first time a command needs them."
    )
