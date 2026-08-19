"""The audit read endpoint: newest-first entries, target filtering, and limit."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from ghl_toolkit.audit import AuditEntry, AuditLog
from server.main import create_app


def _entry(target_id: str, hour: int, tag: str = "hot-lead") -> AuditEntry:
    return AuditEntry(
        ts=datetime(2026, 8, 19, hour, 0, 0, tzinfo=UTC),
        agent="lead_tagger",
        action="contact.add_tags",
        target_type="contact",
        target_id=target_id,
        before=["existing"],
        after=["existing", tag],
        reasoning="Matched the hot-lead rule.",
        mode="api",
        result={"tags": [tag]},
    )


def test_audit_empty_returns_no_entries(server_settings):
    app = create_app(settings=server_settings())
    with TestClient(app) as client:
        response = client.get("/audit")

    assert response.status_code == 200
    assert response.json() == {"entries": []}


def test_audit_filters_by_target_id_newest_first(server_settings):
    settings = server_settings()
    log = AuditLog(settings.audit_log_path)
    log.append(_entry("con_a", hour=10))
    log.append(_entry("con_b", hour=11))
    log.append(_entry("con_a", hour=12))
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/audit", params={"target_id": "con_a"})

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert [entry["target_id"] for entry in entries] == ["con_a", "con_a"]
    timestamps = [datetime.fromisoformat(entry["ts"]) for entry in entries]
    assert timestamps == sorted(timestamps, reverse=True)
    assert timestamps[0].hour == 12


def test_audit_limit_honored(server_settings):
    settings = server_settings()
    log = AuditLog(settings.audit_log_path)
    log.append(_entry("con_a", hour=10))
    log.append(_entry("con_b", hour=11))
    log.append(_entry("con_c", hour=12))
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get("/audit", params={"limit": 1})

    assert response.status_code == 200
    entries = response.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["target_id"] == "con_c"
