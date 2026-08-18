"""The JSONL audit log: append-only writes, configurable path, and read-back."""

import json

from ghl_toolkit.audit import AuditEntry, AuditLog


def _entry(**overrides) -> AuditEntry:
    fields = {
        "agent": "lead_tagger",
        "action": "contact.add_tags",
        "target_type": "contact",
        "target_id": "con_test001",
        "before": ["newsletter"],
        "after": ["newsletter", "hot-lead"],
        "reasoning": "Asked about pricing on the demo call.",
        "mode": "interactive",
        "result": {"tags": ["hot-lead"]},
    }
    fields.update(overrides)
    return AuditEntry(**fields)


def test_append_writes_jsonl_entry(tmp_path):
    path = tmp_path / "audit.jsonl"

    AuditLog(path).append(_entry())

    lines = path.read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["action"] == "contact.add_tags"
    assert record["target_id"] == "con_test001"
    assert record["ts"]


def test_append_only_appends(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append(_entry())
    first_line = path.read_text().splitlines()[0]

    log.append(_entry(target_id="con_test002"))

    lines = path.read_text().splitlines()
    assert len(lines) == 2
    assert lines[0] == first_line
    assert json.loads(lines[1])["target_id"] == "con_test002"


def test_configurable_path_creates_parents(tmp_path):
    path = tmp_path / "deep" / "nested" / "audit.jsonl"

    AuditLog(path).append(_entry())

    assert path.exists()
    assert len(path.read_text().splitlines()) == 1


def test_read_all_round_trips(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path)
    log.append(_entry())
    log.append(_entry(target_id="con_test002", after=["vip"]))

    entries = log.read_all()

    assert [entry.target_id for entry in entries] == ["con_test001", "con_test002"]
    assert entries[0].action == "contact.add_tags"
    assert entries[0].result == {"tags": ["hot-lead"]}
    assert entries[1].after == ["vip"]
