"""FastAPI webhook receiver + proposals API.

The event-driven half of the safety model: a webhook creates a *pending
proposal* — never a write. Humans (or the Phase 6 dashboard) approve or
reject through the proposals API; approval is the only path that applies.

The proposals API carries no authentication in this phase: run it bound to
localhost (the dashboard dev-proxies to it). A forged webhook's blast radius
is a pending proposal a human still has to approve.
"""

import base64
import hmac
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ValidationError

from ghl_toolkit.agents.lead_tagger import (
    TaggingRules,
    TagRule,
    load_rules,
    propose_for_contact,
)
from ghl_toolkit.client import Contact
from ghl_toolkit.llm import (
    AnthropicProvider,
    BudgetExceeded,
    CostBudget,
    LlmClient,
    LlmRefusal,
    MalformedOutputError,
    Provider,
)
from ghl_toolkit.proposals import ProposalStatus, ProposalStore, StoredProposal
from ghl_toolkit.settings import Settings

RULES_PATH = Path("tagging-rules.yaml")

# Used when no tagging-rules.yaml exists beside the server (injected-provider
# tests, demo runs). Mirrors tagging-rules.example.yaml.
_FALLBACK_RULES = TaggingRules(
    tags=[
        TagRule(
            tag="hot-lead",
            when=(
                "The contact shows clear buying intent — asked about pricing, "
                "requested a demo, or came in through a paid campaign."
            ),
        ),
        TagRule(
            tag="newsletter",
            when=(
                "The contact signed up through the newsletter form or downloaded "
                "a lead magnet, but has not expressed buying intent."
            ),
        ),
        TagRule(
            tag="local-market",
            when=(
                "The contact is located in the business's service area (matching "
                "city, state, or surrounding region)."
            ),
        ),
    ]
)


class WebhookResponse(BaseModel):
    """Outcome of one webhook delivery."""

    status: Literal["queued", "ignored", "duplicate", "no_changes"]
    proposals: list[str]


class ProposalList(BaseModel):
    """Wrapper for proposal listings."""

    proposals: list[StoredProposal]


def _resolve_settings(settings: Settings | None) -> Settings | None:
    """Explicit settings win; otherwise load from the environment if complete."""
    if settings is not None:
        return settings
    try:
        return Settings()
    except ValidationError:
        return None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings = app.state.settings
    app.state.store = ProposalStore(settings.proposals_path) if settings is not None else None
    yield


def create_app(
    settings: Settings | None = None,
    provider: Provider | None = None,
    transport: object | None = None,
) -> FastAPI:
    """Build the app; ``provider`` and ``transport`` are injection seams for tests."""
    app = FastAPI(title="ghl-agent-toolkit", lifespan=_lifespan)
    app.state.settings = _resolve_settings(settings)
    app.state.provider = provider
    app.state.transport = transport
    _register_routes(app)
    return app


def _settings_or_503(request: Request) -> Settings:
    settings = request.app.state.settings
    if settings is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Server is not configured — set GHL_API_TOKEN and GHL_LOCATION_ID "
                "(see .env.example)."
            ),
        )
    return settings


def _signature_valid(public_pem: str, signature_b64: str, body: bytes) -> bool:
    try:
        key = load_pem_public_key(public_pem.encode())
        if not isinstance(key, Ed25519PublicKey):
            return False
        key.verify(base64.b64decode(signature_b64), body)
    except (InvalidSignature, ValueError):
        return False
    return True


def _check_webhook_auth(settings: Settings, request: Request, body: bytes) -> None:
    # VERIFY: signed X-GHL-Signature webhooks are documented for Marketplace apps;
    # whether a Private-Integration-only setup receives them is not. Verification is
    # therefore opt-in, with a shared-secret header as the defense for unsigned
    # workflow webhooks. See VERIFY.md (V9).
    if settings.webhook_shared_secret is not None:
        supplied = request.headers.get("X-Webhook-Secret", "")
        expected = settings.webhook_shared_secret.get_secret_value()
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise HTTPException(status_code=401, detail="missing or incorrect X-Webhook-Secret")
    if settings.webhook_verify_signature:
        signature = request.headers.get("X-GHL-Signature")
        if not signature or not _signature_valid(settings.webhook_public_key, signature, body):
            raise HTTPException(status_code=401, detail="missing or invalid X-GHL-Signature")


def _parse_event(body: bytes) -> dict:
    # VERIFY: the integration guide mentions timestamp/webhookId envelope fields the
    # official per-event example does not show; only type/id/locationId are required
    # here and unknown fields are tolerated. Dedup keys on (action, target_id), not
    # webhookId. See VERIFY.md (V10).
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="body is not valid JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail="body must be a JSON object")
    missing = [key for key in ("type", "id", "locationId") if not payload.get(key)]
    if missing:
        raise HTTPException(status_code=422, detail=f"missing required fields: {missing}")
    return payload


def _server_rules() -> TaggingRules:
    if RULES_PATH.exists():
        return load_rules(RULES_PATH)
    return _FALLBACK_RULES


def _build_llm(state) -> LlmClient:
    settings: Settings = state.settings
    provider: Provider | None = state.provider
    if provider is None:
        try:
            provider = AnthropicProvider(settings)
        except ValueError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
    return LlmClient(provider, CostBudget(settings.agent_budget_usd), settings.llm_trace_path)


def _handle_contact_create(state, payload: dict) -> WebhookResponse:
    store: ProposalStore = state.store
    contact = Contact.model_validate(payload)

    pending_ids = [
        record.proposal.id
        for record in store.list(status="pending")
        if record.proposal.action == "contact.add_tags" and record.proposal.target_id == contact.id
    ]
    if pending_ids:
        return WebhookResponse(status="duplicate", proposals=pending_ids)

    llm = _build_llm(state)
    try:
        proposal = propose_for_contact(
            contact, _server_rules(), llm, max_tokens=state.settings.llm_max_tokens
        )
    except (BudgetExceeded, LlmRefusal, MalformedOutputError) as exc:
        raise HTTPException(status_code=503, detail=f"agent could not propose: {exc}") from None
    if proposal is None:
        return WebhookResponse(status="no_changes", proposals=[])
    stored = store.add(proposal, source="webhook")
    return WebhookResponse(status="queued", proposals=[stored.proposal.id])


def _register_routes(app: FastAPI) -> None:
    @app.post("/webhooks/ghl", status_code=202, response_model=WebhookResponse)
    async def receive_webhook(request: Request) -> WebhookResponse:
        settings = _settings_or_503(request)
        body = await request.body()
        _check_webhook_auth(settings, request, body)
        payload = _parse_event(body)
        if payload["type"] != "ContactCreate":
            return WebhookResponse(status="ignored", proposals=[])
        return await run_in_threadpool(_handle_contact_create, request.app.state, payload)

    @app.get("/proposals", response_model=ProposalList)
    def list_proposals(request: Request, status: ProposalStatus | None = None) -> ProposalList:
        _settings_or_503(request)
        return ProposalList(proposals=request.app.state.store.list(status=status))

    @app.get("/proposals/{proposal_id}", response_model=StoredProposal)
    def get_proposal(request: Request, proposal_id: str) -> StoredProposal:
        _settings_or_503(request)
        try:
            return request.app.state.store.get(proposal_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="proposal not found") from None


app = create_app()
