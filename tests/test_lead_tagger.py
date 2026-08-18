"""The lead_tagger agent: rules loading, prompt building, and proposal safety."""

from pathlib import Path

import pytest

from ghl_toolkit.agents.lead_tagger import load_rules, propose_for_contact
from ghl_toolkit.client import Contact
from ghl_toolkit.llm import CostBudget, LlmClient, Usage

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_RULES = REPO_ROOT / "tagging-rules.example.yaml"
FIXTURES = Path(__file__).parent / "fixtures"


def _llm(stub_provider, tmp_path) -> LlmClient:
    return LlmClient(stub_provider, CostBudget(1.0), tmp_path / "trace.jsonl")


def _contact(**overrides) -> Contact:
    fields = {
        "id": "con_test001",
        "first_name": "Jane",
        "last_name": "Testerly",
        "email": "jane@x.test",
        "tags": [],
    }
    fields.update(overrides)
    return Contact(**fields)


def _queued(tags: list[str], reasoning: str = "Asked about pricing.") -> tuple[dict, Usage]:
    return {"tags": tags, "reasoning": reasoning}, Usage(input_tokens=10, output_tokens=5)


def test_rules_load_valid_yaml():
    rules = load_rules(EXAMPLE_RULES)

    assert [rule.tag for rule in rules.tags] == ["hot-lead", "newsletter", "local-market"]
    assert all(rule.when for rule in rules.tags)


def test_rules_invalid_shape_raises():
    with pytest.raises(ValueError):
        load_rules(FIXTURES / "rules_invalid.yaml")


def test_prompt_includes_rules_and_contact(stub_provider, tmp_path):
    stub_provider.queued = [_queued(["hot-lead"])]
    rules = load_rules(EXAMPLE_RULES)

    propose_for_contact(_contact(), rules, _llm(stub_provider, tmp_path))

    system = stub_provider.systems[0]
    for tag in ("hot-lead", "newsletter", "local-market"):
        assert tag in system
    assert "buying intent" in system
    user = stub_provider.users[0]
    assert "Jane" in user
    assert "jane@x.test" in user


def test_invented_tags_filtered(stub_provider, tmp_path):
    stub_provider.queued = [_queued(["hot-lead", "made-up-tag"])]
    rules = load_rules(EXAMPLE_RULES)

    proposal = propose_for_contact(_contact(), rules, _llm(stub_provider, tmp_path))

    assert "hot-lead" in proposal.after
    assert "made-up-tag" not in proposal.after


def test_net_new_only(stub_provider, tmp_path):
    rules = load_rules(EXAMPLE_RULES)
    contact = _contact(tags=["Hot-Lead"])

    stub_provider.queued = [_queued(["hot-lead", "newsletter"])]
    proposal = propose_for_contact(contact, rules, _llm(stub_provider, tmp_path))
    assert proposal.before == ["Hot-Lead"]
    assert proposal.after == ["Hot-Lead", "newsletter"]

    stub_provider.queued = [_queued(["hot-lead"])]
    assert propose_for_contact(contact, rules, _llm(stub_provider, tmp_path)) is None


def test_proposal_shape(stub_provider, tmp_path):
    stub_provider.queued = [_queued(["hot-lead"])]
    rules = load_rules(EXAMPLE_RULES)

    proposal = propose_for_contact(_contact(), rules, _llm(stub_provider, tmp_path))

    assert proposal.id
    assert proposal.agent == "lead_tagger"
    assert proposal.action == "contact.add_tags"
    assert proposal.target_type == "contact"
    assert proposal.target_id == "con_test001"
    assert proposal.before == []
    assert proposal.after == ["hot-lead"]
    assert proposal.reasoning == "Asked about pricing."
    assert "Jane" in proposal.target_label
