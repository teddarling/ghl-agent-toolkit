"""The ghl agent tag command: dry-run gating, interactive apply, and config errors."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from ghl_toolkit.cli import app

BASE_URL = "https://api.test"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
RULES = str(Path(__file__).resolve().parent.parent / "tagging-rules.example.yaml")

runner = CliRunner()


@pytest.fixture
def agent_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GHL_API_TOKEN", "test-token")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc_test123")
    monkeypatch.setenv("GHL_API_BASE_URL", BASE_URL)
    monkeypatch.setenv("GHL_ANTHROPIC_API_KEY", "sk-test-fake-anthropic")
    monkeypatch.setenv("GHL_ANTHROPIC_MODEL", "claude-haiku-4-5")
    monkeypatch.setenv("GHL_AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("GHL_LLM_TRACE_PATH", str(tmp_path / "trace.jsonl"))
    return tmp_path


def _contacts_response(tags_a: list[str] | None = None, tags_b: list[str] | None = None) -> dict:
    return {
        "contacts": [
            {
                "id": "con_a",
                "firstName": "Alice",
                "lastName": "Ada",
                "email": "alice@x.test",
                "tags": tags_a or [],
            },
            {
                "id": "con_b",
                "firstName": "Bob",
                "lastName": "Byte",
                "email": "bob@x.test",
                "tags": tags_b if tags_b is not None else ["hot-lead"],
            },
        ],
        "total": 2,
    }


def _anthropic_response(tags: list[str], reasoning: str) -> dict:
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5",
        "content": [{"type": "text", "text": json.dumps({"tags": tags, "reasoning": reasoning})}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_agent_tag_dry_run_e2e(agent_env):
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(200, json=_contacts_response())
        )
        router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                200, json=_anthropic_response(["hot-lead"], "Asked about pricing.")
            )
        )
        tags_route = router.post(f"{BASE_URL}/contacts/con_a/tags").mock(
            return_value=httpx.Response(201, json={"tags": ["hot-lead"]})
        )
        result = runner.invoke(app, ["agent", "tag", "--rules", RULES])

    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "hot-lead" in result.output
    assert "Asked about pricing." in result.output
    assert "Proposed 1" in result.output
    assert tags_route.call_count == 0
    assert not (agent_env / "audit.jsonl").exists()


def test_agent_tag_apply_yes_e2e(agent_env, load_fixture):
    with respx.mock(assert_all_called=True) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(200, json=_contacts_response())
        )
        router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                200, json=_anthropic_response(["hot-lead"], "Asked about pricing.")
            )
        )
        tags_route = router.post(f"{BASE_URL}/contacts/con_a/tags").mock(
            return_value=httpx.Response(201, json=load_fixture("tags_add_response.json"))
        )
        result = runner.invoke(app, ["agent", "tag", "--apply", "--rules", RULES], input="y\n")

    assert result.exit_code == 0
    assert json.loads(tags_route.calls.last.request.content) == {"tags": ["hot-lead"]}
    audit_lines = (agent_env / "audit.jsonl").read_text().splitlines()
    assert len(audit_lines) == 1
    entry = json.loads(audit_lines[0])
    assert entry["agent"] == "lead_tagger"
    assert entry["action"] == "contact.add_tags"
    assert entry["target_id"] == "con_a"
    assert "hot-lead" in entry["after"]


def test_agent_tag_apply_no_fires_nothing(agent_env):
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(200, json=_contacts_response())
        )
        router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                200, json=_anthropic_response(["hot-lead"], "Asked about pricing.")
            )
        )
        tags_route = router.post(f"{BASE_URL}/contacts/con_a/tags").mock(
            return_value=httpx.Response(201, json={"tags": ["hot-lead"]})
        )
        result = runner.invoke(app, ["agent", "tag", "--apply", "--rules", RULES], input="n\n")

    assert result.exit_code == 0
    assert tags_route.call_count == 0
    assert not (agent_env / "audit.jsonl").exists()


def test_agent_tag_missing_anthropic_key_exit_2(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GHL_API_TOKEN", "test-token")
    monkeypatch.setenv("GHL_LOCATION_ID", "loc_test123")
    monkeypatch.setenv("GHL_API_BASE_URL", BASE_URL)
    monkeypatch.delenv("GHL_ANTHROPIC_API_KEY", raising=False)

    with respx.mock(assert_all_called=False):
        result = runner.invoke(app, ["agent", "tag", "--rules", RULES])

    assert result.exit_code == 2
    assert "GHL_ANTHROPIC_API_KEY" in result.output


def test_agent_tag_missing_rules_exit_2(agent_env):
    with respx.mock(assert_all_called=False):
        result = runner.invoke(app, ["agent", "tag"])

    assert result.exit_code == 2
    assert "tagging-rules.example.yaml" in result.output


def test_agent_tag_budget_exceeded_exit_1(agent_env, monkeypatch):
    monkeypatch.setenv("GHL_AGENT_BUDGET_USD", "0.000001")
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(200, json=_contacts_response(tags_b=[]))
        )
        anthropic_route = router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                200, json=_anthropic_response(["hot-lead"], "Asked about pricing.")
            )
        )
        result = runner.invoke(app, ["agent", "tag", "--rules", RULES])

    assert result.exit_code == 1
    assert "budget" in result.output.lower()
    assert anthropic_route.call_count == 1


def test_agent_tag_no_proposals_exit_0(agent_env):
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(200, json=_contacts_response())
        )
        router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, json=_anthropic_response([], "No rules apply."))
        )
        tags_route = router.post(f"{BASE_URL}/contacts/con_a/tags").mock(
            return_value=httpx.Response(201, json={"tags": []})
        )
        result = runner.invoke(app, ["agent", "tag", "--dry-run", "--rules", RULES])

    assert result.exit_code == 0
    assert "Proposed 0" in result.output
    assert tags_route.call_count == 0
