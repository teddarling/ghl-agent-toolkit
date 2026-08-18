"""Demo mode: the full propose → approve → apply loop with zero credentials."""

import json
from pathlib import Path

import respx
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from ghl_toolkit.agents.lead_tagger import TagProposal, load_rules
from ghl_toolkit.cli import app as cli_app
from ghl_toolkit.demo import DemoProvider
from ghl_toolkit.llm import Usage
from server.main import create_app

EXAMPLE_RULES = Path(__file__).resolve().parent.parent / "tagging-rules.example.yaml"
EXAMPLE_PAYLOAD = Path(__file__).resolve().parent.parent / "examples" / "contact_created.json"

runner = CliRunner()


def test_server_seeds_pending_in_demo(demo_env):
    app = create_app()

    with TestClient(app) as client:
        pending = client.get("/proposals", params={"status": "pending"}).json()["proposals"]

    assert len(pending) >= 1
    assert all(record["source"] == "demo-seed" for record in pending)


def test_demo_approve_fully_offline(demo_env):
    app = create_app()

    with TestClient(app) as client:
        pending = client.get("/proposals", params={"status": "pending"}).json()["proposals"]
        proposal_id = pending[0]["proposal"]["id"]

        # A zero-route respx mock: any HTTP over a real transport would error here.
        with respx.mock:
            response = client.post(f"/proposals/{proposal_id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    audit_lines = (demo_env / "audit.jsonl").read_text().splitlines()
    assert len(audit_lines) == 1
    assert json.loads(audit_lines[0])["action"] == "contact.add_tags"


def test_demo_provider_deterministic():
    provider = DemoProvider()
    rules = load_rules(EXAMPLE_RULES)
    system = "Allowed tags:\n" + "\n".join(f"- {r.tag}: {r.when}" for r in rules.tags)
    user = "Contact:\nName: Wanda Hookins\nSource: website newsletter signup"

    first, usage_one = provider.complete(
        system=system, user=user, response_model=TagProposal, max_tokens=256
    )
    second, usage_two = provider.complete(
        system=system, user=user, response_model=TagProposal, max_tokens=256
    )

    assert provider.model == "demo"
    assert first == second
    assert usage_one == usage_two == Usage(input_tokens=0, output_tokens=0)
    assert "newsletter" in first.tags
    assert first.reasoning.startswith("Demo mode:")


def test_demo_webhook_flow(demo_env):
    payload = json.loads(EXAMPLE_PAYLOAD.read_text())
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/webhooks/ghl", json=payload)
        assert response.status_code == 202
        assert response.json()["status"] == "queued"

        pending = client.get("/proposals", params={"status": "pending"}).json()["proposals"]

    assert any(record["proposal"]["target_id"] == "con_webhook001" for record in pending)


def test_cli_agent_tag_demo_dry_run(demo_env):
    with respx.mock:
        result = runner.invoke(cli_app, ["agent", "tag"])

    assert result.exit_code == 0
    assert "Proposed" in result.output
    assert "Configuration incomplete" not in result.output
