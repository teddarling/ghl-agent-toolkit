"""The proposals API: list, get, approve (the only apply path), and reject."""

import json

import httpx
import respx
from fastapi.testclient import TestClient

from ghl_toolkit.agents.harness import Proposal
from ghl_toolkit.proposals import ProposalStore
from server.main import create_app

BASE_URL = "https://api.test"


def _seed_pending(
    settings,
    contact_id: str = "con_a",
    before: list[str] | None = None,
    new_tags: list[str] | None = None,
):
    """Write a pending proposal to the store file the app will load."""
    before = list(before or [])
    proposal = Proposal(
        agent="lead_tagger",
        action="contact.add_tags",
        target_type="contact",
        target_id=contact_id,
        target_label="Alice Ada",
        before=before,
        after=[*before, *(new_tags or ["hot-lead"])],
        reasoning="Asked about pricing.",
    )
    return ProposalStore(settings.proposals_path).add(proposal, source="webhook")


def test_list_empty(server_settings):
    app = create_app(settings=server_settings())
    with TestClient(app) as client:
        assert client.get("/proposals").json() == {"proposals": []}


def test_list_filters_by_status(server_settings):
    settings = server_settings()
    pending = _seed_pending(settings, contact_id="con_a")
    rejected = _seed_pending(settings, contact_id="con_b")
    ProposalStore(settings.proposals_path).update(rejected.proposal.id, status="rejected")
    app = create_app(settings=settings)

    with TestClient(app) as client:
        pending_ids = [
            record["proposal"]["id"]
            for record in client.get("/proposals", params={"status": "pending"}).json()["proposals"]
        ]
        rejected_ids = [
            record["proposal"]["id"]
            for record in client.get("/proposals", params={"status": "rejected"}).json()[
                "proposals"
            ]
        ]

    assert pending_ids == [pending.proposal.id]
    assert rejected_ids == [rejected.proposal.id]


def test_get_single_proposal(server_settings):
    settings = server_settings()
    stored = _seed_pending(settings)
    app = create_app(settings=settings)

    with TestClient(app) as client:
        response = client.get(f"/proposals/{stored.proposal.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["proposal"]["id"] == stored.proposal.id
    assert body["status"] == "pending"


def test_approve_applies_and_audits(server_settings, load_fixture):
    settings = server_settings()
    stored = _seed_pending(settings, before=["existing"], new_tags=["hot-lead"])
    app = create_app(settings=settings)

    with TestClient(app) as client, respx.mock(base_url=BASE_URL) as router:
        tags_route = router.post("/contacts/con_a/tags").mock(
            return_value=httpx.Response(201, json=load_fixture("tags_add_response.json"))
        )
        response = client.post(f"/proposals/{stored.proposal.id}/approve")

    assert response.status_code == 200
    assert response.json()["status"] == "applied"
    assert json.loads(tags_route.calls.last.request.content) == {"tags": ["hot-lead"]}

    audit_lines = settings.audit_log_path.read_text().splitlines()
    assert len(audit_lines) == 1
    entry = json.loads(audit_lines[0])
    assert entry["action"] == "contact.add_tags"
    assert entry["target_id"] == "con_a"
    assert entry["mode"] == "api"


def test_approve_missing_404(server_settings):
    app = create_app(settings=server_settings())
    with TestClient(app) as client:
        assert client.post("/proposals/nope/approve").status_code == 404


def test_double_approve_409(server_settings, load_fixture):
    settings = server_settings()
    stored = _seed_pending(settings)
    app = create_app(settings=settings)

    with TestClient(app) as client, respx.mock(base_url=BASE_URL) as router:
        tags_route = router.post("/contacts/con_a/tags").mock(
            return_value=httpx.Response(201, json=load_fixture("tags_add_response.json"))
        )
        first = client.post(f"/proposals/{stored.proposal.id}/approve")
        second = client.post(f"/proposals/{stored.proposal.id}/approve")

    assert first.status_code == 200
    assert second.status_code == 409
    assert tags_route.call_count == 1


def test_approve_apply_failure_marks_failed(server_settings):
    settings = server_settings()
    stored = _seed_pending(settings)
    app = create_app(settings=settings)

    with TestClient(app) as client, respx.mock(base_url=BASE_URL) as router:
        tags_route = router.post("/contacts/con_a/tags").mock(
            return_value=httpx.Response(500, json={"message": "server exploded"})
        )
        response = client.post(f"/proposals/{stored.proposal.id}/approve")
        record = client.get(f"/proposals/{stored.proposal.id}").json()

    # Phase 2 policy: POST 5xx is never retried — exactly one attempt.
    assert tags_route.call_count == 1
    assert response.status_code == 502
    assert "failed" in response.text
    assert record["status"] == "failed"
    assert record["error"]
    assert not settings.audit_log_path.exists()


def test_reject_no_write_no_audit(server_settings):
    settings = server_settings()
    stored = _seed_pending(settings)
    app = create_app(settings=settings)

    with TestClient(app) as client, respx.mock:
        response = client.post(f"/proposals/{stored.proposal.id}/reject")

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert not settings.audit_log_path.exists()


def test_healthz_no_config(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for var in ("GHL_API_TOKEN", "GHL_LOCATION_ID", "GHL_ANTHROPIC_API_KEY", "GHL_DEMO_MODE"):
        monkeypatch.delenv(var, raising=False)
    app = create_app()

    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "demo_mode" in body
