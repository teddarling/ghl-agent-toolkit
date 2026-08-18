"""The lead_tagger agent: proposes tags for recent contacts from a rules file.

The rules file is the whole vocabulary — a tag the model invents that is not
in the rules can never reach a proposal; it is dropped deterministically after
validation. Only net-new tags (case-insensitive against the contact's existing
tags) are proposed, and the harness gates every apply.
"""

from collections.abc import Callable
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from ghl_toolkit.agents.harness import Proposal
from ghl_toolkit.client import Contact
from ghl_toolkit.llm import LlmClient

AGENT_NAME = "lead_tagger"
ACTION = "contact.add_tags"


class TagRule(BaseModel):
    """One tag the agent is allowed to propose, and when it applies."""

    tag: str
    when: str


class TaggingRules(BaseModel):
    """The rules file: the complete set of proposable tags."""

    tags: list[TagRule] = Field(min_length=1)

    @field_validator("tags")
    @classmethod
    def _unique_tags(cls, rules: list[TagRule]) -> list[TagRule]:
        seen: set[str] = set()
        for rule in rules:
            lowered = rule.tag.lower()
            if lowered in seen:
                raise ValueError(f"duplicate tag in rules: {rule.tag!r}")
            seen.add(lowered)
        return rules


class TagProposal(BaseModel):
    """The model's structured answer: proposed tags plus its reasoning."""

    tags: list[str]
    reasoning: str


def load_rules(path: Path | str) -> TaggingRules:
    """Load and validate the tagging rules YAML."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return TaggingRules.model_validate(data)


def _system_prompt(rules: TaggingRules) -> str:
    rule_lines = "\n".join(f"- {rule.tag}: {rule.when}" for rule in rules.tags)
    return (
        "You tag CRM contacts for a small business. Decide which of the allowed "
        "tags apply to the contact, using each tag's criteria. Choose only from "
        "the allowed tags; return an empty list if none apply, and explain your "
        "reasoning in one or two sentences.\n\n"
        f"Allowed tags:\n{rule_lines}"
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
        ("Existing tags", ", ".join(contact.tags)),
    )
    lines = "\n".join(f"{label}: {value}" for label, value in fields if value)
    return f"Contact:\n{lines}"


def _target_label(contact: Contact) -> str:
    full_name = " ".join(part for part in (contact.first_name, contact.last_name) if part)
    return contact.name or full_name or contact.email or contact.id


def propose_for_contact(
    contact: Contact,
    rules: TaggingRules,
    llm: LlmClient,
    *,
    max_tokens: int = 4096,
    on_invented: Callable[[str], None] | None = None,
) -> Proposal | None:
    """Ask the model which rule tags apply; return a proposal of net-new tags, or None."""
    parsed, _usage = llm.complete(
        system=_system_prompt(rules),
        user=_user_prompt(contact),
        response_model=TagProposal,
        max_tokens=max_tokens,
    )

    canonical = {rule.tag.lower(): rule.tag for rule in rules.tags}
    allowed: list[str] = []
    for tag in parsed.tags:
        match = canonical.get(tag.lower())
        if match is None:
            if on_invented is not None:
                on_invented(tag)
        elif match not in allowed:
            allowed.append(match)

    existing = {tag.lower() for tag in contact.tags}
    net_new = [tag for tag in allowed if tag.lower() not in existing]
    if not net_new:
        return None

    return Proposal(
        agent=AGENT_NAME,
        action=ACTION,
        target_type="contact",
        target_id=contact.id,
        target_label=_target_label(contact),
        before=list(contact.tags),
        after=[*contact.tags, *net_new],
        reasoning=parsed.reasoning,
    )
