"""The propose → approve → apply engine shared by every agent.

Agent-agnostic and interface-free: no CLI or rendering imports, so the
webhook server can drive the same flow headless. Dry-run is structural —
in that mode neither the approver nor the apply function is ever invoked.
"""

from collections.abc import Callable, Iterable
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from ghl_toolkit.audit import AuditEntry, AuditLog
from ghl_toolkit.client import ApiError


class Proposal(BaseModel):
    """A proposed change to one record: never a direct write."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    agent: str
    action: str
    target_type: str
    target_id: str
    target_label: str
    before: object = None
    after: object = None
    reasoning: str


class HarnessResult(BaseModel):
    """Counts and audit entries from one harness run."""

    proposed: int = 0
    approved: int = 0
    applied: int = 0
    rejected: int = 0
    errors: int = 0
    applied_entries: list[AuditEntry] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)


def run_proposals(
    proposals: Iterable[Proposal],
    *,
    mode: Literal["dry_run", "apply"],
    approver: Callable[[Proposal], bool],
    apply_fn: Callable[[Proposal], object],
    audit_log: AuditLog,
    audit_mode: str = "interactive",
) -> HarnessResult:
    """Run proposals through the gate; only approved ones reach apply_fn.

    An ApiError from one apply is counted and the batch continues — one bad
    record must not kill the run. Rejections write nothing: the audit log is
    the record of writes, and a rejection writes nothing.
    """
    items = list(proposals)
    result = HarnessResult(proposed=len(items))
    if mode == "dry_run":
        return result

    for proposal in items:
        if not approver(proposal):
            result.rejected += 1
            continue
        result.approved += 1
        try:
            outcome = apply_fn(proposal)
        except ApiError as exc:
            result.errors += 1
            result.error_messages.append(str(exc))
            continue
        entry = AuditEntry(
            agent=proposal.agent,
            action=proposal.action,
            target_type=proposal.target_type,
            target_id=proposal.target_id,
            before=proposal.before,
            after=proposal.after,
            reasoning=proposal.reasoning,
            mode=audit_mode,
            result=outcome,
        )
        audit_log.append(entry)
        result.applied += 1
        result.applied_entries.append(entry)
    return result
