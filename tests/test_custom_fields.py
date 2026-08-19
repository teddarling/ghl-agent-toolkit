"""Custom-field lookup and safe score-field resolution for the lead_scorer."""

import httpx
import pytest
import respx

from ghl_toolkit.client.custom_fields import list_custom_fields, resolve_score_field

BASE_URL = "https://api.test"


def test_list_custom_fields_query_and_path(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/locations/loc_test123/customFields").mock(
            return_value=httpx.Response(200, json=load_fixture("custom_fields_response.json"))
        )
        fields = list_custom_fields(client)

    assert route.calls.last.request.url.params["model"] == "contact"
    assert [field.id for field in fields] == ["cf_notes001", "cf_score001", "cf_budget001"]
    assert fields[1].field_key == "contact.lead_score"


def test_resolve_score_field_by_key(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/locations/loc_test123/customFields").mock(
            return_value=httpx.Response(200, json=load_fixture("custom_fields_response.json"))
        )
        field_id = resolve_score_field(client, field_key="lead_score")

    assert field_id == "cf_score001"


def test_resolve_missing_field_clear_error(client, load_fixture):
    fixture = load_fixture("custom_fields_response.json")
    fixture["customFields"] = [
        field for field in fixture["customFields"] if field["id"] != "cf_score001"
    ]

    with respx.mock(base_url=BASE_URL) as router:
        router.get("/locations/loc_test123/customFields").mock(
            return_value=httpx.Response(200, json=fixture)
        )
        with pytest.raises((LookupError, ValueError)) as exc_info:
            resolve_score_field(client, field_key="lead_score")

    message = str(exc_info.value)
    assert "GHL_SCORE_FIELD_ID" in message
    assert "custom field" in message.lower()
