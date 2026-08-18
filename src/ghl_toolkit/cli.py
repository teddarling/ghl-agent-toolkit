"""Typer CLI entry point for the ghl command."""

import importlib.metadata
import textwrap
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import httpx
import typer
from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ghl_toolkit.agents.harness import Proposal, run_proposals
from ghl_toolkit.agents.lead_tagger import load_rules, propose_for_contact
from ghl_toolkit.audit import AuditLog
from ghl_toolkit.client import (
    ApiError,
    AuthError,
    GHLClient,
    NotFound,
    add_contact_tags,
    get_contact,
    search_contacts,
    search_conversations,
    search_opportunities,
)
from ghl_toolkit.llm import (
    AnthropicProvider,
    BudgetExceeded,
    CostBudget,
    LlmClient,
    LlmRefusal,
    MalformedOutputError,
)
from ghl_toolkit.settings import Settings, get_settings

app = typer.Typer(no_args_is_help=True)
contacts_app = typer.Typer(no_args_is_help=True)
opps_app = typer.Typer(no_args_is_help=True)
convos_app = typer.Typer(no_args_is_help=True)
agent_app = typer.Typer(no_args_is_help=True)
app.add_typer(contacts_app, name="contacts", help="Inspect contacts.")
app.add_typer(opps_app, name="opps", help="Inspect opportunities.")
app.add_typer(convos_app, name="convos", help="Inspect conversations.")
app.add_typer(agent_app, name="agent", help="Run gated agents (propose → approve → apply).")
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
APPLY_OPTION = typer.Option(
    False,
    "--apply/--dry-run",
    help="Apply approved proposals (default is dry-run: propose only, write nothing).",
)
AGENT_LIMIT_OPTION = typer.Option(10, "--limit", help="How many recent contacts to consider.")
RULES_OPTION = typer.Option(
    Path("tagging-rules.yaml"), "--rules", help="Path to the tagging rules file."
)
BUDGET_OPTION = typer.Option(
    None, "--budget", help="Per-run USD budget for LLM calls (default from settings)."
)


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


def _proposal_panel(proposal: Proposal) -> Panel:
    before = ", ".join(proposal.before) if proposal.before else "(none)"
    added = [tag for tag in proposal.after if tag not in proposal.before]
    body = (
        f"[bold]Tags:[/bold] {before} → [green]{', '.join(proposal.after)}[/green]\n"
        f"[bold]Adds:[/bold] {', '.join(added)}\n"
        f"[bold]Reasoning:[/bold] {proposal.reasoning}"
    )
    return Panel(body, title=f"{proposal.target_label} ({proposal.target_id})", box=box.SQUARE)


@agent_app.command("tag")
def agent_tag(
    apply: bool = APPLY_OPTION,
    limit: int = AGENT_LIMIT_OPTION,
    rules_path: Path = RULES_OPTION,
    budget: float | None = BUDGET_OPTION,
) -> None:
    """Propose tags for recent contacts; apply only what you approve."""
    settings = _load_settings_or_exit()
    if settings.anthropic_api_key is None:
        console.print(
            "[red]✗[/red] GHL_ANTHROPIC_API_KEY is not set — agent commands need an "
            "Anthropic API key. Add it to your .env."
        )
        raise typer.Exit(2)
    if not rules_path.exists():
        console.print(
            f"[red]✗[/red] Rules file not found: {rules_path}\n"
            "Copy the example and edit it for your business:\n"
            "    cp tagging-rules.example.yaml tagging-rules.yaml"
        )
        raise typer.Exit(2)
    try:
        rules = load_rules(rules_path)
    except ValidationError as exc:
        console.print(f"[red]✗[/red] Invalid rules file {rules_path}:\n{exc}")
        raise typer.Exit(2) from None

    llm = LlmClient(
        AnthropicProvider(settings),
        CostBudget(budget if budget is not None else settings.agent_budget_usd),
        settings.llm_trace_path,
    )
    audit_log = AuditLog(settings.audit_log_path)

    with _client_or_exit() as client:
        page = search_contacts(client, limit=limit)

        proposals: list[Proposal] = []
        no_changes = 0
        try:
            for contact in page.contacts:
                proposal = propose_for_contact(
                    contact,
                    rules,
                    llm,
                    max_tokens=settings.llm_max_tokens,
                    on_invented=lambda tag: console.print(
                        f"[yellow]⚠[/yellow] Dropped tag not in the rules: {tag!r}"
                    ),
                )
                if proposal is None:
                    no_changes += 1
                else:
                    proposals.append(proposal)
                    console.print(_proposal_panel(proposal))
        except BudgetExceeded as exc:
            console.print(f"[red]✗[/red] Stopped: {exc}")
            raise typer.Exit(1) from None
        except LlmRefusal as exc:
            console.print(f"[red]✗[/red] The model refused: {exc}")
            raise typer.Exit(1) from None
        except MalformedOutputError:
            console.print("[red]✗[/red] The model kept returning invalid output; giving up.")
            raise typer.Exit(1) from None

        result = run_proposals(
            proposals,
            mode="apply" if apply else "dry_run",
            approver=lambda p: typer.confirm(f"Apply to {p.target_label}?"),
            apply_fn=lambda p: add_contact_tags(
                client, p.target_id, [tag for tag in p.after if tag not in p.before]
            ),
            audit_log=audit_log,
        )

    console.print(
        f"Proposed {result.proposed} · approved {result.approved} · "
        f"applied {result.applied} · rejected {result.rejected} · no changes {no_changes}"
    )
    if not apply and result.proposed:
        console.print("Dry run — nothing was written. Re-run with --apply to approve changes.")
    if result.errors:
        console.print(f"[red]✗[/red] {result.errors} apply call(s) failed — see messages above.")
        raise typer.Exit(1)
