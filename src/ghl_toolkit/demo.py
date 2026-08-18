"""Demo mode: the full propose → approve → apply loop with zero credentials.

Seeded fake contacts, a deterministic keyword provider, and an in-process
``httpx.MockTransport`` standing in for the HighLevel API — so the server and
the CLI can be exercised (and screen-recorded) without a GHL account, an
Anthropic key, or any network access. Everything here is embedded constants:
demo mode works wherever the package is installed.
"""

import json
import os
import re

import httpx
from pydantic import SecretStr

from ghl_toolkit.agents.lead_tagger import TaggingRules, TagRule
from ghl_toolkit.llm import Usage
from ghl_toolkit.settings import Settings

DEMO_LOCATION_ID = "demo_location"

# Mirrors tagging-rules.example.yaml so the demo tells the same story the
# committed example does.
DEMO_RULES = TaggingRules(
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

# Field names follow the documented contact schema; values are obviously fake.
# Sources deliberately mention rule-tag keywords so DemoProvider's substring
# matching yields plausible proposals — and one contact matches nothing, to
# show the no-changes path.
DEMO_CONTACTS: list[dict] = [
    {
        "id": "con_demo001",
        "locationId": DEMO_LOCATION_ID,
        "firstName": "Priya",
        "lastName": "Kapoor",
        "name": "Priya Kapoor",
        "email": "priya@example.test",
        "phone": "+15550100001",
        "tags": [],
        "dateAdded": "2026-08-14T09:15:00.000Z",
        "city": "Springfield",
        "state": "IL",
        "country": "US",
        "source": "newsletter signup form",
    },
    {
        "id": "con_demo002",
        "locationId": DEMO_LOCATION_ID,
        "firstName": "Marcus",
        "lastName": "Webb",
        "name": "Marcus Webb",
        "email": "marcus@example.test",
        "phone": "+15550100002",
        "tags": [],
        "dateAdded": "2026-08-15T14:40:00.000Z",
        "city": "Springfield",
        "state": "IL",
        "country": "US",
        "companyName": "Webb Roofing",
        "source": "home show booth — local-market outreach",
    },
    {
        "id": "con_demo003",
        "locationId": DEMO_LOCATION_ID,
        "firstName": "Dana",
        "lastName": "Ruiz",
        "name": "Dana Ruiz",
        "email": "dana@example.test",
        "phone": "+15550100003",
        "tags": ["customer"],
        "dateAdded": "2026-08-16T11:05:00.000Z",
        "city": "Chatham",
        "state": "IL",
        "country": "US",
        "source": "pricing page hot-lead form",
    },
    {
        "id": "con_demo004",
        "locationId": DEMO_LOCATION_ID,
        "firstName": "Ellis",
        "lastName": "Trent",
        "name": "Ellis Trent",
        "email": "ellis@example.test",
        "phone": "+15550100004",
        "tags": [],
        "dateAdded": "2026-08-17T16:30:00.000Z",
        "city": "Denver",
        "state": "CO",
        "country": "US",
        "source": "cold list import",
    },
]

_RULE_LINE = re.compile(r"-\s*([A-Za-z0-9_-]+):")


class DemoProvider:
    """Deterministic stand-in for the LLM: keyword-matches rule tags against the contact.

    Reads the allowed tags out of the same system prompt the real provider
    gets, proposes every tag whose name appears in the contact text, and costs
    nothing. Identical input always produces identical output.
    """

    model = "demo"

    def complete(self, *, system: str, user: str, response_model, max_tokens: int):
        haystack = user.lower()
        tags = []
        for line in system.splitlines():
            match = _RULE_LINE.match(line.strip())
            if match and match.group(1).lower() in haystack:
                tags.append(match.group(1))
        matched = ", ".join(tags) if tags else "no rule keywords"
        parsed = response_model.model_validate(
            {
                "tags": tags,
                "reasoning": f"Demo mode: matched {matched} against the contact's details.",
            }
        )
        return parsed, Usage(input_tokens=0, output_tokens=0)


def demo_active() -> bool:
    """Whether GHL_DEMO_MODE is switched on in the environment."""
    return os.environ.get("GHL_DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def demo_settings() -> Settings:
    """Settings for a credential-free demo run; store paths still come from the env."""
    return Settings(
        _env_file=None,
        demo_mode=True,
        api_token=SecretStr("demo-token"),
        location_id=DEMO_LOCATION_ID,
    )


def demo_transport() -> httpx.MockTransport:
    """An in-process HighLevel API serving the demo contacts — zero network."""
    contacts = {entry["id"]: entry for entry in DEMO_CONTACTS}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/contacts/search":
            return httpx.Response(
                200, json={"contacts": DEMO_CONTACTS, "total": len(DEMO_CONTACTS)}
            )
        if request.method == "POST" and path.startswith("/contacts/") and path.endswith("/tags"):
            tags = json.loads(request.content)["tags"]
            return httpx.Response(201, json={"tags": tags})
        if request.method == "GET" and path.startswith("/contacts/"):
            contact = contacts.get(path.removeprefix("/contacts/"))
            if contact is None:
                return httpx.Response(404, json={"message": "contact not found"})
            return httpx.Response(200, json={"contact": contact})
        return httpx.Response(404, json={"message": f"no demo route for {request.method} {path}"})

    return httpx.MockTransport(handler)
