"""The webhook endpoint: event handling, dedup, auth, and GHL retry-safety."""

import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from ghl_toolkit.llm import Usage
from server.main import create_app

USAGE = Usage(input_tokens=100, output_tokens=20)


def _contact_create(contact_id: str = "con_hook1", tags: list[str] | None = None) -> dict:
    return {
        "type": "ContactCreate",
        "locationId": "loc_test123",
        "id": contact_id,
        "firstName": "Wanda",
        "lastName": "Hookins",
        "name": "Wanda Hookins",
        "email": "wanda@x.test",
        "phone": "+15550100999",
        "tags": tags or [],
        "dateAdded": "2026-08-18T12:00:00.000Z",
        "city": "Springfield",
        "state": "IL",
        "country": "US",
        "source": "website form",
        "companyName": "Hookins Heating",
    }


def _queue_tags(stub, tags: list[str], reasoning: str = "Buying intent.") -> None:
    stub.queued.append(({"tags": tags, "reasoning": reasoning}, USAGE))


def test_contact_create_creates_pending_proposal(server_settings, stub_provider):
    _queue_tags(stub_provider, ["hot-lead"])
    app = create_app(settings=server_settings(), provider=stub_provider)

    with TestClient(app) as client:
        response = client.post("/webhooks/ghl", json=_contact_create())
        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "queued"
        assert len(body["proposals"]) == 1

        stored = client.get(f"/proposals/{body['proposals'][0]}").json()

    assert stored["status"] == "pending"
    assert stored["source"] == "webhook"
    assert stored["proposal"]["target_id"] == "con_hook1"
    assert stored["proposal"]["before"] == []
    assert stored["proposal"]["after"] == ["hot-lead"]


def test_unknown_event_type_ignored(server_settings, stub_provider):
    app = create_app(settings=server_settings(), provider=stub_provider)

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/ghl",
            json={"type": "ContactDelete", "id": "con_x", "locationId": "loc_test123"},
        )
        assert response.status_code == 202
        assert response.json()["status"] == "ignored"
        assert client.get("/proposals").json()["proposals"] == []
    assert stub_provider.calls == 0


def test_malformed_body_422(server_settings, stub_provider):
    app = create_app(settings=server_settings(), provider=stub_provider)

    with TestClient(app) as client:
        not_json = client.post(
            "/webhooks/ghl", content=b"not json", headers={"content-type": "application/json"}
        )
        assert not_json.status_code == 422

        missing_fields = client.post("/webhooks/ghl", json={"type": "ContactCreate"})
        assert missing_fields.status_code == 422


def test_duplicate_pending_dedupes(server_settings, stub_provider):
    _queue_tags(stub_provider, ["hot-lead"])
    _queue_tags(stub_provider, ["hot-lead"])
    app = create_app(settings=server_settings(), provider=stub_provider)

    with TestClient(app) as client:
        first = client.post("/webhooks/ghl", json=_contact_create()).json()
        second = client.post("/webhooks/ghl", json=_contact_create())

        assert second.status_code == 202
        assert second.json()["status"] == "duplicate"
        assert second.json()["proposals"] == first["proposals"]
        assert len(client.get("/proposals", params={"status": "pending"}).json()["proposals"]) == 1


def test_shared_secret_enforced(server_settings, stub_provider):
    _queue_tags(stub_provider, ["hot-lead"])
    settings = server_settings(webhook_shared_secret="hook-secret")
    app = create_app(settings=settings, provider=stub_provider)

    with TestClient(app) as client:
        assert client.post("/webhooks/ghl", json=_contact_create()).status_code == 401
        wrong = client.post(
            "/webhooks/ghl", json=_contact_create(), headers={"X-Webhook-Secret": "wrong"}
        )
        assert wrong.status_code == 401
        right = client.post(
            "/webhooks/ghl", json=_contact_create(), headers={"X-Webhook-Secret": "hook-secret"}
        )
        assert right.status_code == 202
        assert right.json()["status"] == "queued"


def test_no_net_new_tags_returns_empty(server_settings, stub_provider):
    _queue_tags(stub_provider, ["hot-lead"])
    app = create_app(settings=server_settings(), provider=stub_provider)

    with TestClient(app) as client:
        response = client.post("/webhooks/ghl", json=_contact_create(tags=["hot-lead"]))
        assert response.status_code == 202
        assert response.json() == {"status": "no_changes", "proposals": []}
        assert client.get("/proposals").json()["proposals"] == []


def test_missing_anthropic_key_503(server_settings):
    app = create_app(settings=server_settings(anthropic_api_key=None))

    with TestClient(app) as client:
        response = client.post("/webhooks/ghl", json=_contact_create())

    assert response.status_code == 503
    assert "GHL_ANTHROPIC_API_KEY" in response.text


def _signing_setup():
    private_key = Ed25519PrivateKey.generate()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode()
    )
    return private_key, public_pem


def test_valid_ed25519_signature_accepted(server_settings, stub_provider):
    private_key, public_pem = _signing_setup()
    _queue_tags(stub_provider, ["hot-lead"])
    settings = server_settings(webhook_verify_signature=True, webhook_public_key=public_pem)
    app = create_app(settings=settings, provider=stub_provider)

    body = json.dumps(_contact_create()).encode()
    signature = base64.b64encode(private_key.sign(body)).decode()

    with TestClient(app) as client:
        response = client.post(
            "/webhooks/ghl",
            content=body,
            headers={"content-type": "application/json", "X-GHL-Signature": signature},
        )

    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_invalid_signature_401(server_settings, stub_provider):
    private_key, public_pem = _signing_setup()
    settings = server_settings(webhook_verify_signature=True, webhook_public_key=public_pem)
    app = create_app(settings=settings, provider=stub_provider)

    body = json.dumps(_contact_create()).encode()
    wrong_signature = base64.b64encode(private_key.sign(b"different body")).decode()

    with TestClient(app) as client:
        missing = client.post(
            "/webhooks/ghl", content=body, headers={"content-type": "application/json"}
        )
        assert missing.status_code == 401

        wrong = client.post(
            "/webhooks/ghl",
            content=body,
            headers={"content-type": "application/json", "X-GHL-Signature": wrong_signature},
        )
        assert wrong.status_code == 401
    assert stub_provider.calls == 0
