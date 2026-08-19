"""The lead_scorer agent: scores leads against a rubric, gated like every write.

The score lands in a contact custom field, but only through the harness's
apply step, and only ever to a field id that was resolved or verified
read-only first — a write to the wrong field is impossible by construction.
Out-of-range scores fail pydantic validation and ride the malformed-output
retry loop instead of reaching a proposal.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ghl_toolkit.agents.harness import Proposal
from ghl_toolkit.client import Contact
from ghl_toolkit.llm import LlmClient

AGENT_NAME = "lead_scorer"
ACTION = "contact.set_score"


class ScoreCriterion(BaseModel):
    """One rubric criterion and the points it is worth."""

    name: str
    when: str
    points: int


class ScoringRubric(BaseModel):
    """The rubric file: criteria summing to the intended score scale."""

    criteria: list[ScoreCriterion] = Field(min_length=1)


class ScoreProposal(BaseModel):
    """The model's structured answer: a bounded score plus its reasoning."""

    score: int = Field(ge=0, le=100)
    reasoning: str


def load_rubric(path: Path | str) -> ScoringRubric:
    """Load and validate the scoring rubric YAML."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ScoringRubric.model_validate(data)


def _system_prompt(rubric: ScoringRubric) -> str:
    criterion_lines = "\n".join(
        f"- {criterion.name} ({criterion.points} points): {criterion.when}"
        for criterion in rubric.criteria
    )
    return (
        "You score CRM leads for a small business on a 0-100 scale. Award points "
        "for each rubric criterion the contact meets, sum them, and explain your "
        "reasoning in one or two sentences.\n\n"
        f"Rubric:\n{criterion_lines}"
    )


def _user_prompt(contact: Contact) -> str:
    full_name = " ".join(part for part in (contact.first_name, contact.last_name) if part)
    fields = (
        ("Name", contact.name or full_name),
        ("Email", contact.email),
        ("Phone", contact.phone),
        ("City", contact.city),
        ("State", contact.state),
        ("Country", contact.country),
        ("Source", contact.source),
        ("Company", contact.company_name),
        ("Tags", ", ".join(contact.tags)),
    )
    lines = "\n".join(f"{label}: {value}" for label, value in fields if value)
    return f"Contact:\n{lines}"


def _target_label(contact: Contact) -> str:
    full_name = " ".join(part for part in (contact.first_name, contact.last_name) if part)
    return contact.name or full_name or contact.email or contact.id


def _current_value(contact: Contact, field_id: str) -> str | None:
    for field in contact.custom_fields:
        if field.id == field_id and field.value is not None:
            return str(field.value)
    return None


def propose_score(
    contact: Contact,
    rubric: ScoringRubric,
    llm: LlmClient,
    *,
    field_id: str,
    max_tokens: int = 4096,
) -> Proposal | None:
    """Score the contact against the rubric; None when the score is already current."""
    parsed, _usage = llm.complete(
        system=_system_prompt(rubric),
        user=_user_prompt(contact),
        response_model=ScoreProposal,
        max_tokens=max_tokens,
    )
    before = _current_value(contact, field_id)
    after = str(parsed.score)
    if before == after:
        return None

    return Proposal(
        agent=AGENT_NAME,
        action=ACTION,
        target_type="contact",
        target_id=contact.id,
        target_label=_target_label(contact),
        before=before,
        after=after,
        reasoning=parsed.reasoning,
    )
