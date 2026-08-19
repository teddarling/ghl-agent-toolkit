"""The lead_scorer agent: rubric loading, score bounds, and the gated field write."""

import json
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import ValidationError

from ghl_toolkit.agents.lead_scorer import ScoreProposal, load_rubric, propose_score
from ghl_toolkit.client import Contact
from ghl_toolkit.client.custom_fields import set_contact_custom_field
from ghl_toolkit.llm import CostBudget, LlmClient, MalformedOutputError, Usage

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_RUBRIC = REPO_ROOT / "scoring-rubric.example.yaml"
BASE_URL = "https://api.test"


def _llm(stub_provider, tmp_path) -> LlmClient:
    return LlmClient(stub_provider, CostBudget(1.0), tmp_path / "trace.jsonl")


def _contact(**overrides) -> Contact:
    fields = {
        "id": "con_test001",
        "firstName": "Jane",
        "lastName": "Tester",
        "email": "jane@x.test",
        "phone": "+15550000001",
        "customFields": [{"id": "cf_score001", "value": "40"}],
    }
    fields.update(overrides)
    return Contact.model_validate(fields)


def _queued(score: int, reasoning: str = "Strong buying intent.") -> tuple[dict, Usage]:
    return {"score": score, "reasoning": reasoning}, Usage(input_tokens=10, output_tokens=5)


def test_rubric_load_valid_yaml():
    rubric = load_rubric(EXAMPLE_RUBRIC)

    names = [criterion.name for criterion in rubric.criteria]
    assert names == ["buying-intent", "reachable", "local", "engaged"]
    assert all(criterion.when for criterion in rubric.criteria)
    assert all(isinstance(criterion.points, int) for criterion in rubric.criteria)


def test_rubric_invalid_shape_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("criteria: not-a-list\n")

    with pytest.raises(ValueError):
        load_rubric(bad)


def test_prompt_includes_rubric_and_contact(stub_provider, tmp_path):
    stub_provider.queued = [_queued(85)]
    rubric = load_rubric(EXAMPLE_RUBRIC)

    propose_score(_contact(), rubric, _llm(stub_provider, tmp_path), field_id="cf_score001")

    system = stub_provider.systems[0]
    assert "buying-intent" in system
    assert "pricing" in system
    user = stub_provider.users[0]
    assert "jane@x.test" in user


def test_score_out_of_bounds_rides_malformed_retry(stub_provider, tmp_path):
    with pytest.raises(ValidationError):
        ScoreProposal(score=150, reasoning="too high")
    with pytest.raises(ValidationError):
        ScoreProposal(score=-5, reasoning="too low")

    stub_provider.queued = [
        MalformedOutputError('{"score": 150}', "score: less than or equal to 100"),
        _queued(85),
    ]
    rubric = load_rubric(EXAMPLE_RUBRIC)

    proposal = propose_score(
        _contact(), rubric, _llm(stub_provider, tmp_path), field_id="cf_score001"
    )

    assert proposal is not None
    assert stub_provider.calls == 2


def test_proposal_before_after_field_values(stub_provider, tmp_path):
    rubric = load_rubric(EXAMPLE_RUBRIC)

    stub_provider.queued = [_queued(85)]
    proposal = propose_score(
        _contact(), rubric, _llm(stub_provider, tmp_path), field_id="cf_score001"
    )
    assert proposal.agent == "lead_scorer"
    assert proposal.action == "contact.set_score"
    assert proposal.target_type == "contact"
    assert proposal.target_id == "con_test001"
    assert proposal.before == "40"
    assert proposal.after == "85"
    assert proposal.reasoning == "Strong buying intent."

    stub_provider.queued = [_queued(85)]
    no_field = _contact(customFields=[])
    proposal = propose_score(
        no_field, rubric, _llm(stub_provider, tmp_path), field_id="cf_score001"
    )
    assert proposal.before is None
    assert proposal.after == "85"


def test_apply_puts_resolved_field_id_only(client):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.put("/contacts/con_test001").mock(
            return_value=httpx.Response(
                200, json={"succeeded": True, "contact": {"id": "con_test001"}}
            )
        )
        set_contact_custom_field(client, "con_test001", "cf_score001", "85")

    body = json.loads(route.calls.last.request.content)
    assert body == {"customFields": [{"id": "cf_score001", "fieldValue": "85"}]}
