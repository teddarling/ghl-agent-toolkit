"""Typer CLI entry point for the ghl command."""

import importlib.metadata
import textwrap
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

import httpx
import typer
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.table import Table

from ghl_toolkit.client import (
    ApiError,
    AuthError,
    GHLClient,
    NotFound,
    get_contact,
    search_contacts,
    search_conversations,
    search_opportunities,
)
from ghl_toolkit.settings import Settings, get_settings

app = typer.Typer(no_args_is_help=True)
contacts_app = typer.Typer(no_args_is_help=True)
opps_app = typer.Typer(no_args_is_help=True)
convos_app = typer.Typer(no_args_is_help=True)
app.add_typer(contacts_app, name="contacts", help="Inspect contacts.")
app.add_typer(opps_app, name="opps", help="Inspect opportunities.")
app.add_typer(convos_app, name="convos", help="Inspect conversations.")
console = Console()

RATE_LIMIT_HEADERS = (
    "X-RateLimit-Limit-Daily",
    "X-RateLimit-Daily-Remaining",
    "X-RateLimit-Interval-Milliseconds",
    "X-RateLimit-Max",
    "X-RateLimit-Remaining",
)

LIMIT_OPTION = typer.Option(20, "--limit", help="Maximum records to fetch (API max 100).")
JSON_OPTION = typer.Option(False, "--json", help="Print the raw response as JSON.")


def _load_settings_or_exit() -> Settings:
    """Return validated settings, or exit 2 with a hint when configuration is missing."""
    try:
        return get_settings()
    except ValidationError as exc:
        missing = ", ".join(f"GHL_{str(err['loc'][0]).upper()}" for err in exc.errors())
        console.print(f"[red]✗[/red] Configuration incomplete — missing: {missing}")
        console.print("Copy .env.example to .env and fill in your HighLevel credentials.")
        raise typer.Exit(2) from None


@contextmanager
def _client_or_exit() -> Iterator[GHLClient]:
    """Yield a configured client, translating API failures into exit code 1."""
    settings = _load_settings_or_exit()
    try:
        with GHLClient(settings) as client:
            yield client
    except AuthError as exc:
        console.print(f"[red]✗[/red] Authorization failed ({exc.status_code}): {exc.message}")
        raise typer.Exit(1) from None
    except ApiError as exc:
        console.print(f"[red]✗[/red] API error {exc.status_code}: {exc.message}")
        raise typer.Exit(1) from None
    except httpx.HTTPError as exc:
        console.print(f"[red]✗[/red] Request failed: {exc}")
        raise typer.Exit(1) from None


def _dash(value: str | None) -> str:
    return value if value else "—"


def _date(value: datetime | None) -> str:
    return value.date().isoformat() if value else "—"


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
    settings = _load_settings_or_exit()

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


@contacts_app.command("list")
def contacts_list(limit: int = LIMIT_OPTION, json_output: bool = JSON_OPTION) -> None:
    """List recent contacts for the configured location."""
    with _client_or_exit() as client:
        page = search_contacts(client, limit=limit)

    if json_output:
        typer.echo(page.model_dump_json(indent=2))
        return
    if not page.contacts:
        console.print("No contacts found.")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("ID", overflow="fold", min_width=11)
    table.add_column("Name", overflow="fold")
    table.add_column("Email", overflow="fold", min_width=11)
    table.add_column("Phone", overflow="fold")
    table.add_column("Tags", overflow="fold")
    table.add_column("Added", overflow="fold")
    for contact in page.contacts:
        full_name = " ".join(p for p in (contact.first_name, contact.last_name) if p)
        table.add_row(
            contact.id,
            _dash(contact.name or full_name),
            _dash(contact.email),
            _dash(contact.phone),
            _dash(", ".join(contact.tags)),
            _date(contact.date_added),
        )
    console.print(table)
    if page.total is not None:
        console.print(f"Showing {len(page.contacts)} of {page.total} contacts.")


@contacts_app.command("get")
def contacts_get(contact_id: str, json_output: bool = JSON_OPTION) -> None:
    """Show a single contact by id."""
    with _client_or_exit() as client:
        try:
            contact = get_contact(client, contact_id)
        except NotFound:
            console.print(f"[red]✗[/red] Contact {contact_id} not found — check the id.")
            raise typer.Exit(1) from None

    if json_output:
        typer.echo(contact.model_dump_json(indent=2))
        return

    full_name = " ".join(p for p in (contact.first_name, contact.last_name) if p)
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    rows = (
        ("ID", contact.id),
        ("Name", _dash(contact.name or full_name)),
        ("Email", _dash(contact.email)),
        ("Phone", _dash(contact.phone)),
        ("Tags", _dash(", ".join(contact.tags))),
        ("Company", _dash(contact.company_name)),
        ("City", _dash(contact.city)),
        ("State", _dash(contact.state)),
        ("Country", _dash(contact.country)),
        ("Source", _dash(contact.source)),
        ("Assigned to", _dash(contact.assigned_to)),
        ("Added", _date(contact.date_added)),
        ("Updated", _date(contact.date_updated)),
    )
    for field, value in rows:
        table.add_row(field, value)
    console.print(table)


@opps_app.command("list")
def opps_list(limit: int = LIMIT_OPTION, json_output: bool = JSON_OPTION) -> None:
    """List recent opportunities for the configured location."""
    with _client_or_exit() as client:
        page = search_opportunities(client, limit=limit)

    if json_output:
        typer.echo(page.model_dump_json(indent=2))
        return
    if not page.opportunities:
        console.print("No opportunities found.")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("ID", overflow="fold", min_width=11)
    table.add_column("Name", overflow="fold")
    table.add_column("Status", overflow="fold")
    table.add_column("Value", overflow="fold")
    table.add_column("Stage", overflow="fold")
    table.add_column("Created", overflow="fold")
    for opp in page.opportunities:
        value = f"{opp.monetary_value:,.2f}" if opp.monetary_value is not None else "—"
        table.add_row(
            opp.id,
            _dash(opp.name),
            _dash(opp.status),
            value,
            _dash(opp.pipeline_stage_id),
            _date(opp.created_at),
        )
    console.print(table)
    if page.meta is not None and page.meta.total is not None:
        console.print(f"Showing {len(page.opportunities)} of {page.meta.total} opportunities.")


@convos_app.command("list")
def convos_list(limit: int = LIMIT_OPTION, json_output: bool = JSON_OPTION) -> None:
    """List recent conversations for the configured location."""
    with _client_or_exit() as client:
        page = search_conversations(client, limit=limit)

    if json_output:
        typer.echo(page.model_dump_json(indent=2))
        return
    if not page.conversations:
        console.print("No conversations found.")
        return

    table = Table(box=box.SIMPLE)
    table.add_column("ID", overflow="fold", min_width=12)
    table.add_column("Contact", overflow="fold")
    table.add_column("Last message", overflow="fold")
    table.add_column("Type", overflow="fold")
    table.add_column("Unread", overflow="fold")
    for convo in page.conversations:
        last_message = (
            textwrap.shorten(convo.last_message_body, width=40, placeholder="…")
            if convo.last_message_body
            else "—"
        )
        unread = str(convo.unread_count) if convo.unread_count is not None else "—"
        table.add_row(
            convo.id,
            _dash(convo.contact_name or convo.full_name),
            last_message,
            _dash(convo.last_message_type),
            unread,
        )
    console.print(table)
    console.print(f"Showing {len(page.conversations)} of {page.total} conversations.")
