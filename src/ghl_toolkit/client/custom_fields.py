"""Custom-field lookup and the lead_scorer's gated field write.

Discovery endpoints come from the official OpenAPI spec (``apps/locations.json``
in github.com/GoHighLevel/highlevel-api-docs): ``GET /locations/{locationId}/
customFields`` (scope ``locations/customFields.readonly``) and its get-by-id
sibling. The toolkit never creates fields — writing schema objects into a
client CRM uninvited would violate the gating ethos; the user creates the
field in GHL and the toolkit resolves it read-only.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ghl_toolkit.client.http import GHLClient


class CustomField(BaseModel):
    """A location custom field, curated to the documented schema."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    name: str | None = None
    field_key: str | None = None
    data_type: str | None = None
    model: str | None = None


def list_custom_fields(client: GHLClient, *, model: str = "contact") -> list[CustomField]:
    """Return the location's custom fields (scope locations/customFields.readonly)."""
    response = client.get(
        f"/locations/{client.settings.location_id}/customFields", params={"model": model}
    )
    payload = response.json()
    fields = payload.get("customFields", []) if isinstance(payload, dict) else []
    return [CustomField.model_validate(field) for field in fields]


def get_custom_field(client: GHLClient, field_id: str) -> CustomField:
    """Return one custom field by id — used to verify an explicitly configured id."""
    response = client.get(f"/locations/{client.settings.location_id}/customFields/{field_id}")
    return CustomField.model_validate(response.json()["customField"])


def resolve_score_field(client: GHLClient, *, field_key: str = "lead_score") -> str:
    """Resolve the score field's id by key, read-only; the apply path uses only this id."""
    fields = list_custom_fields(client)
    matches = [
        field
        for field in fields
        if field.field_key is not None
        and (field.field_key == field_key or field.field_key.endswith(f".{field_key}"))
    ]
    if not matches:
        raise LookupError(
            f"No contact custom field with key {field_key!r} exists in this location. "
            "Create the field in GHL (Settings → Custom Fields), or set "
            "GHL_SCORE_FIELD_ID to the id of the field to use."
        )
    if len(matches) > 1:
        ids = ", ".join(field.id for field in matches)
        raise LookupError(
            f"Multiple custom fields match key {field_key!r} ({ids}) — set "
            "GHL_SCORE_FIELD_ID to pick one explicitly."
        )
    return matches[0].id


def set_contact_custom_field(client: GHLClient, contact_id: str, field_id: str, value: str) -> dict:
    """Write one custom-field value via PUT /contacts/{contactId} (scope contacts.write).

    Returns the response body ({"succeeded": ..., "contact": {...}}) for the audit log.
    """
    # VERIFY: the exact member set of a customFields write item is not machine-verifiable —
    # UpdateContactDto is truncated in the official spec; {"id", "fieldValue"} follows the
    # rendered marketplace example. See VERIFY.md (V11).
    body = {"customFields": [{"id": field_id, "fieldValue": value}]}
    response = client.put(f"/contacts/{contact_id}", json=body)
    return response.json()
