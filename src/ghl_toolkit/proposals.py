"""Persistent proposal queue shared by the webhook server, CLI, and dashboard.

Append-only JSONL, mirroring the audit log: every add or status change appends
a full record, and the latest record per proposal id wins on reload. That makes
the file crash-safe and human-inspectable, at the cost of one line per change —
the right trade at this scale.
"""

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ghl_toolkit.agents.harness import Proposal

ProposalStatus = Literal["pending", "applied", "rejected", "failed"]


class StoredProposal(BaseModel):
    """A proposal plus its lifecycle state in the queue."""

    proposal: Proposal
    status: ProposalStatus = "pending"
    source: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    error: str | None = None
    result: dict | None = None


class ProposalStore:
    """Thread-safe, file-backed proposal queue at a configurable path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._records: dict[str, StoredProposal] = {}
        self._order: list[str] = []
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                record = StoredProposal.model_validate_json(line)
                self._remember(record)

    def _remember(self, record: StoredProposal) -> None:
        proposal_id = record.proposal.id
        if proposal_id not in self._records:
            self._order.append(proposal_id)
        self._records[proposal_id] = record

    def _append_line(self, record: StoredProposal) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(record.model_dump_json() + "\n")

    def add(self, proposal: Proposal, *, source: str) -> StoredProposal:
        """Store a new proposal as pending and return its record."""
        record = StoredProposal(proposal=proposal, source=source)
        with self._lock:
            self._remember(record)
            self._append_line(record)
        return record

    def get(self, proposal_id: str) -> StoredProposal:
        """Return the current record for the id; raises KeyError when absent."""
        return self._records[proposal_id]

    def list(self, *, status: ProposalStatus | None = None) -> list[StoredProposal]:
        """Return records newest-first, optionally filtered by status."""
        records = [self._records[proposal_id] for proposal_id in reversed(self._order)]
        if status is None:
            return records
        return [record for record in records if record.status == status]

    def update(self, proposal_id: str, **changes: object) -> StoredProposal:
        """Apply changes to a record, stamp decided_at on status changes, and persist."""
        with self._lock:
            current = self._records[proposal_id]
            if "status" in changes and "decided_at" not in changes:
                changes["decided_at"] = datetime.now(UTC)
            record = current.model_copy(update=changes)
            self._remember(record)
            self._append_line(record)
        return record
