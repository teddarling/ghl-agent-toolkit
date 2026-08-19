"""The reply_drafter agent: guidelines, drafting, and the inert-by-construction apply."""

from pathlib import Path

import pytest
import respx

from ghl_toolkit.agents.reply_drafter import apply_draft, load_guidelines, propose_for_conversation
from ghl_toolkit.client import Conversation, Message
from ghl_toolkit.llm import CostBudget, LlmClient, Usage

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_GUIDELINES = REPO_ROOT / "reply-guidelines.example.yaml"


def _llm(stub_provider, tmp_path) -> LlmClient:
    return LlmClient(stub_provider, CostBudget(1.0), tmp_path / "trace.jsonl")


def _conversation(**overrides) -> Conversation:
    fields = {
        "id": "conv_test001",
        "contact_id": "con_test001",
        "contact_name": "Jane Tester",
        "email": "jane@x.test",
        "last_message_body": "Hi - do you have pricing for a kitchen remodel?",
        "type": "TYPE_SMS",
    }
    fields.update(overrides)
    return Conversation(**fields)


def _messages(load_fixture) -> list[Message]:
    return [
        Message.model_validate(raw) for raw in load_fixture("messages_response.json")["messages"]
    ]


def _queued(draft: str, reasoning: str = "Asked about pricing.") -> tuple[dict, Usage]:
    return {"draft": draft, "reasoning": reasoning}, Usage(input_tokens=10, output_tokens=5)


def test_guidelines_load_valid_yaml():
    guidelines = load_guidelines(EXAMPLE_GUIDELINES)

    assert "home-services" in guidelines.business_context
    assert guidelines.tone
    assert len(guidelines.guidelines) >= 3


def test_guidelines_invalid_shape_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("tone: []\nguidelines: not-a-list\n")

    with pytest.raises(ValueError):
        load_guidelines(bad)


def test_prompt_includes_messages_and_guidelines(stub_provider, tmp_path, load_fixture):
    stub_provider.queued = [_queued("Hi Jane - happy to help with pricing.")]
    guidelines = load_guidelines(EXAMPLE_GUIDELINES)

    propose_for_conversation(
        _conversation(), _messages(load_fixture), guidelines, _llm(stub_provider, tmp_path)
    )

    system = stub_provider.systems[0]
    assert "no hard sell" in system
    assert "Never invent prices" in system
    user = stub_provider.users[0]
    assert "kitchen remodel" in user
    assert "Jane" in user


def test_skips_conversation_with_no_inbound_body(stub_provider, tmp_path, load_fixture):
    guidelines = load_guidelines(EXAMPLE_GUIDELINES)
    no_inbound = [
        message
        for message in _messages(load_fixture)
        if message.direction != "inbound" or message.body is None
    ]

    proposal = propose_for_conversation(
        _conversation(), no_inbound, guidelines, _llm(stub_provider, tmp_path)
    )

    assert proposal is None
    assert stub_provider.calls == 0


def test_proposal_shape_draft_reply(stub_provider, tmp_path, load_fixture):
    stub_provider.queued = [_queued("Hi Jane - happy to help with pricing.")]
    guidelines = load_guidelines(EXAMPLE_GUIDELINES)

    proposal = propose_for_conversation(
        _conversation(), _messages(load_fixture), guidelines, _llm(stub_provider, tmp_path)
    )

    assert proposal.id
    assert proposal.agent == "reply_drafter"
    assert proposal.action == "conversation.draft_reply"
    assert proposal.target_type == "conversation"
    assert proposal.target_id == "conv_test001"
    assert proposal.before is None
    assert proposal.after["draft"] == "Hi Jane - happy to help with pricing."
    assert proposal.reasoning == "Asked about pricing."
    assert "Jane" in proposal.target_label


def test_apply_is_inert_zero_http(stub_provider, tmp_path, load_fixture):
    stub_provider.queued = [_queued("Hi Jane - happy to help with pricing.")]
    guidelines = load_guidelines(EXAMPLE_GUIDELINES)
    proposal = propose_for_conversation(
        _conversation(), _messages(load_fixture), guidelines, _llm(stub_provider, tmp_path)
    )

    # Zero-route respx: any HTTP request over a real transport would error here.
    with respx.mock:
        result = apply_draft(proposal)

    assert result["delivered"] is False
    assert result["note"]
