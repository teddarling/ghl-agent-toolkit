"""The reply_drafter agent: drafts replies to inbound conversations for human review.

This agent has no send capability at all — not gated, absent. Its apply step
takes no client and makes no HTTP call: approving a draft records it in the
audit log for a human to copy into GoHighLevel. The README's promise ("it
never sends on its own") is enforced by construction, not by configuration.
"""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ghl_toolkit.agents.harness import Proposal
from ghl_toolkit.client import Conversation, Message
from ghl_toolkit.llm import LlmClient

AGENT_NAME = "reply_drafter"
ACTION = "conversation.draft_reply"


class ReplyGuidelines(BaseModel):
    """The guidelines file: business context, tone, and drafting rules."""

    business_context: str
    tone: str
    guidelines: list[str] = Field(min_length=1)


class DraftProposal(BaseModel):
    """The model's structured answer: the draft plus its reasoning."""

    draft: str
    reasoning: str


def load_guidelines(path: Path | str) -> ReplyGuidelines:
    """Load and validate the reply guidelines YAML."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return ReplyGuidelines.model_validate(data)


def _system_prompt(guidelines: ReplyGuidelines) -> str:
    rule_lines = "\n".join(f"- {rule}" for rule in guidelines.guidelines)
    return (
        "You draft a reply to the customer's latest inbound message for a human "
        "to review and send. Write only the reply text — no signature, no "
        "placeholders — and explain your reasoning in one or two sentences.\n\n"
        f"Business context: {guidelines.business_context}\n"
        f"Tone: {guidelines.tone}\n"
        f"Guidelines:\n{rule_lines}"
    )


def _user_prompt(conversation: Conversation, inbound: list[Message]) -> str:
    contact = conversation.contact_name or conversation.full_name or conversation.email or ""
    transcript = "\n".join(f"[{message.direction}] {message.body}" for message in inbound)
    header = f"Conversation with {contact}".strip()
    return f"{header}\n{transcript}\nDraft a reply to the latest inbound message."


def _target_label(conversation: Conversation) -> str:
    return (
        conversation.contact_name or conversation.full_name or conversation.email or conversation.id
    )


def propose_for_conversation(
    conversation: Conversation,
    messages: list[Message],
    guidelines: ReplyGuidelines,
    llm: LlmClient,
    *,
    max_tokens: int = 4096,
) -> Proposal | None:
    """Draft a reply to the conversation's inbound messages, or None if there are none."""
    inbound = [message for message in messages if message.direction == "inbound" and message.body]
    if not inbound:
        return None

    parsed, _usage = llm.complete(
        system=_system_prompt(guidelines),
        user=_user_prompt(conversation, inbound),
        response_model=DraftProposal,
        max_tokens=max_tokens,
    )
    return Proposal(
        agent=AGENT_NAME,
        action=ACTION,
        target_type="conversation",
        target_id=conversation.id,
        target_label=_target_label(conversation),
        before=None,
        after={"draft": parsed.draft},
        reasoning=parsed.reasoning,
    )


def apply_draft(proposal: Proposal) -> dict:
    """The drafter's apply step: record-only, deliberately inert.

    Takes no client and performs no HTTP call — there is no code path from an
    approved draft to a sent message. The returned dict lands in the audit
    entry's result field.
    """
    return {
        "delivered": False,
        "note": "draft only — copy the approved reply into GoHighLevel to send it",
        "draft": proposal.after["draft"] if isinstance(proposal.after, dict) else None,
    }
