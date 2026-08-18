"""The propose-approve-apply harness: gating, auditing, and error isolation."""

from ghl_toolkit.agents.harness import Proposal, run_proposals
from ghl_toolkit.audit import AuditLog
from ghl_toolkit.client import ApiError


def _proposal(pid: str = "prop-1", target_id: str = "con_test001") -> Proposal:
    return Proposal(
        id=pid,
        agent="lead_tagger",
        action="contact.add_tags",
        target_type="contact",
        target_id=target_id,
        target_label="Jane Testerly",
        before=["newsletter"],
        after=["newsletter", "hot-lead"],
        reasoning="Asked about pricing.",
    )


def test_dry_run_never_applies(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    approver_calls: list[Proposal] = []
    apply_calls: list[Proposal] = []

    def approver(proposal: Proposal) -> bool:
        approver_calls.append(proposal)
        return True

    result = run_proposals(
        [_proposal(), _proposal("prop-2", "con_test002")],
        mode="dry_run",
        approver=approver,
        apply_fn=lambda p: apply_calls.append(p),
        audit_log=AuditLog(audit_path),
    )

    assert result.proposed == 2
    assert result.applied == 0
    assert approver_calls == []
    assert apply_calls == []
    assert not audit_path.exists()


def test_approved_proposal_applied_and_audited(tmp_path):
    audit_path = tmp_path / "audit.jsonl"

    result = run_proposals(
        [_proposal()],
        mode="apply",
        approver=lambda p: True,
        apply_fn=lambda p: {"tags": ["hot-lead"]},
        audit_log=AuditLog(audit_path),
    )

    assert result.approved == 1
    assert result.applied == 1
    entries = AuditLog(audit_path).read_all()
    assert len(entries) == 1
    assert entries[0].agent == "lead_tagger"
    assert entries[0].action == "contact.add_tags"
    assert entries[0].target_id == "con_test001"
    assert entries[0].result == {"tags": ["hot-lead"]}


def test_rejected_proposal_skips_apply_no_audit(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    apply_calls: list[Proposal] = []

    result = run_proposals(
        [_proposal()],
        mode="apply",
        approver=lambda p: False,
        apply_fn=lambda p: apply_calls.append(p),
        audit_log=AuditLog(audit_path),
    )

    assert result.rejected == 1
    assert result.applied == 0
    assert apply_calls == []
    assert not audit_path.exists()


def test_apply_error_continues(tmp_path):
    audit_path = tmp_path / "audit.jsonl"

    def apply_fn(proposal: Proposal) -> dict:
        if proposal.target_id == "con_test001":
            raise ApiError(500, "server error", {}, "POST", "https://api.test/x")
        return {"tags": ["hot-lead"]}

    result = run_proposals(
        [_proposal(), _proposal("prop-2", "con_test002")],
        mode="apply",
        approver=lambda p: True,
        apply_fn=apply_fn,
        audit_log=AuditLog(audit_path),
    )

    assert result.errors == 1
    assert result.applied == 1
    entries = AuditLog(audit_path).read_all()
    assert len(entries) == 1
    assert entries[0].target_id == "con_test002"


def test_mixed_decisions_counts(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    decisions = {"prop-1": True, "prop-2": False, "prop-3": True}
    proposals = [
        _proposal("prop-1", "con_test001"),
        _proposal("prop-2", "con_test002"),
        _proposal("prop-3", "con_test003"),
    ]

    result = run_proposals(
        proposals,
        mode="apply",
        approver=lambda p: decisions[p.id],
        apply_fn=lambda p: {"tags": ["hot-lead"]},
        audit_log=AuditLog(audit_path),
    )

    assert result.proposed == 3
    assert result.approved == 2
    assert result.applied == 2
    assert result.rejected == 1
    assert result.errors == 0
    assert len(AuditLog(audit_path).read_all()) == 2
