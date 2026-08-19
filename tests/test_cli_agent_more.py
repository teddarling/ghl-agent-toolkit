"""The ghl agent draft and score commands, plus friendly LLM failure handling."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from ghl_toolkit.cli import app

BASE_URL = "https://api.test"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
REPO_ROOT = Path(__file__).resolve().parent.parent
RULES = str(REPO_ROOT / "tagging-rules.example.yaml")
RUBRIC = str(REPO_ROOT / "scoring-rubric.example.yaml")

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


def _anthropic_body(text: str) -> dict:
    return {
        "id": "msg_test123",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-4-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def test_agent_draft_dry_run_demo(demo_env):
    with respx.mock:
        result = runner.invoke(app, ["agent", "draft"])

    assert result.exit_code == 0
    assert "Proposed" in result.output
    assert "Demo mode:" in result.output


def test_agent_draft_apply_audits_without_http(demo_env):
    with respx.mock:
        result = runner.invoke(app, ["agent", "draft", "--apply"], input="y\n" * 8)

    assert result.exit_code == 0
    audit_lines = (demo_env / "audit.jsonl").read_text().splitlines()
    assert len(audit_lines) >= 1
    assert all(json.loads(line)["action"] == "conversation.draft_reply" for line in audit_lines)


def test_agent_score_dry_run_demo(demo_env):
    with respx.mock:
        result = runner.invoke(app, ["agent", "score"])

    assert result.exit_code == 0
    assert "Proposed" in result.output
    assert "Demo mode:" in result.output


def test_agent_score_apply_e2e(agent_env, load_fixture):
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(200, json=load_fixture("contacts_search_page1.json"))
        )
        router.get(f"{BASE_URL}/locations/loc_test123/customFields").mock(
            return_value=httpx.Response(200, json=load_fixture("custom_fields_response.json"))
        )
        put_route = router.put(url__regex=rf"{BASE_URL}/contacts/con_test\d+$").mock(
            return_value=httpx.Response(200, json={"succeeded": True, "contact": {}})
        )
        router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                200,
                json=_anthropic_body(
                    json.dumps({"score": 85, "reasoning": "Strong buying intent."})
                ),
            )
        )
        result = runner.invoke(
            app, ["agent", "score", "--apply", "--rubric", RUBRIC], input="y\n" * 3
        )

    assert result.exit_code == 0
    assert put_route.called
    for call in put_route.calls:
        assert json.loads(call.request.content) == {
            "customFields": [{"id": "cf_score001", "fieldValue": "85"}]
        }
    audit_lines = (agent_env / "audit.jsonl").read_text().splitlines()
    assert len(audit_lines) >= 1
    assert all(json.loads(line)["action"] == "contact.set_score" for line in audit_lines)


def test_anthropic_401_friendly_exit_1(agent_env):
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(
                200,
                json={"contacts": [{"id": "con_a", "firstName": "Alice", "tags": []}], "total": 1},
            )
        )
        router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(
                401,
                json={
                    "type": "error",
                    "error": {
                        "type": "authentication_error",
                        "message": "API key is invalid.",
                    },
                },
            )
        )
        result = runner.invoke(app, ["agent", "tag", "--rules", RULES])

    assert result.exit_code == 1
    assert "GHL_ANTHROPIC_API_KEY" in result.output
    assert "Traceback" not in result.output


def test_malformed_output_detail_shown(agent_env):
    with respx.mock(assert_all_called=False) as router:
        router.post(f"{BASE_URL}/contacts/search").mock(
            return_value=httpx.Response(
                200,
                json={"contacts": [{"id": "con_a", "firstName": "Alice", "tags": []}], "total": 1},
            )
        )
        router.post(ANTHROPIC_URL).mock(
            return_value=httpx.Response(200, json=_anthropic_body("this is not json"))
        )
        result = runner.invoke(app, ["agent", "tag", "--rules", RULES])

    assert result.exit_code == 1
    assert "valid" in result.output.lower()
    assert "trace.jsonl" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    ("command", "example_file"),
    [
        ("draft", "reply-guidelines.example.yaml"),
        ("score", "scoring-rubric.example.yaml"),
    ],
)
def test_agent_missing_config_files_exit_2(agent_env, command, example_file):
    with respx.mock(assert_all_called=False):
        result = runner.invoke(app, ["agent", command])

    assert result.exit_code == 2
    assert example_file in result.output
