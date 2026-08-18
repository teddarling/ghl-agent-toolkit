"""The committed example payload must stay accepted by the webhook forever."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from server.main import create_app

EXAMPLE_PAYLOAD = Path(__file__).resolve().parent.parent / "examples" / "contact_created.json"


def test_example_payload_accepted_by_webhook(demo_env):
    payload = json.loads(EXAMPLE_PAYLOAD.read_text())
    app = create_app()

    with TestClient(app) as client:
        response = client.post("/webhooks/ghl", json=payload)
        assert response.status_code == 202
        proposal_ids = response.json()["proposals"]
        assert len(proposal_ids) == 1

        stored = client.get(f"/proposals/{proposal_ids[0]}").json()

    assert stored["status"] == "pending"
    assert stored["proposal"]["target_id"] == payload["id"]
