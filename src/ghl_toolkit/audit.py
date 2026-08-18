"""Append-only JSONL audit log: one entry for every write the toolkit applies."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field


class AuditEntry(BaseModel):
    """A single applied change: what changed, which agent proposed it, and the outcome."""

    ts: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent: str
    action: str
    target_type: str
    target_id: str
    before: object = None
    after: object = None
    reasoning: str
    mode: str = "interactive"
    result: object = None


class AuditLog:
    """Append-only JSONL writer and reader at a configurable path."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def append(self, entry: AuditEntry) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def read_all(self) -> list[AuditEntry]:
        if not self.path.exists():
            return []
        return [
            AuditEntry.model_validate_json(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
