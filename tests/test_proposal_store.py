"""The JSONL proposal store: append-only persistence with last-record-per-id wins."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from ghl_toolkit.agents.harness import Proposal
from ghl_toolkit.proposals import ProposalStore


def _proposal(n: int) -> Proposal:
    return Proposal(
        agent="lead_tagger",
        action="contact.add_tags",
        target_type="contact",
        target_id=f"con_{n}",
        target_label=f"Contact {n}",
        before=[],
        after=["hot-lead"],
        reasoning="Asked about pricing.",
    )


def test_append_and_list_pending(tmp_path):
    store = ProposalStore(tmp_path / "proposals.jsonl")
    stored = store.add(_proposal(1), source="webhook")

    assert stored.status == "pending"
    assert stored.source == "webhook"
    assert stored.proposal.target_id == "con_1"
    listed = store.list(status="pending")
    assert [record.proposal.id for record in listed] == [stored.proposal.id]


def test_update_status_applied_persists(tmp_path):
    path = tmp_path / "proposals.jsonl"
    store = ProposalStore(path)
    stored = store.add(_proposal(1), source="webhook")

    store.update(stored.proposal.id, status="applied", result={"tags": ["hot-lead"]})

    got = store.get(stored.proposal.id)
    assert got.status == "applied"
    assert got.result == {"tags": ["hot-lead"]}
    assert len(path.read_text().splitlines()) == 2


def test_get_missing_id_raises(tmp_path):
    store = ProposalStore(tmp_path / "proposals.jsonl")
    with pytest.raises(KeyError):
        store.get("nope")


def test_reload_reads_last_status(tmp_path):
    path = tmp_path / "proposals.jsonl"
    store = ProposalStore(path)
    stored = store.add(_proposal(1), source="webhook")
    store.update(stored.proposal.id, status="rejected")

    reloaded = ProposalStore(path)
    assert reloaded.get(stored.proposal.id).status == "rejected"
    assert len(reloaded.list()) == 1


def test_list_filters_by_status(tmp_path):
    store = ProposalStore(tmp_path / "proposals.jsonl")
    first = store.add(_proposal(1), source="webhook")
    second = store.add(_proposal(2), source="webhook")
    store.update(second.proposal.id, status="applied")

    assert [r.proposal.id for r in store.list(status="pending")] == [first.proposal.id]
    assert [r.proposal.id for r in store.list(status="applied")] == [second.proposal.id]
    # Unfiltered list is newest-first.
    assert [r.proposal.id for r in store.list()] == [second.proposal.id, first.proposal.id]


def test_concurrent_updates_safe(tmp_path):
    path = tmp_path / "proposals.jsonl"
    store = ProposalStore(path)
    ids = [store.add(_proposal(n), source="webhook").proposal.id for n in range(12)]

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda pid: store.update(pid, status="applied"), ids))

    reloaded = ProposalStore(path)
    assert len(reloaded.list(status="applied")) == 12
