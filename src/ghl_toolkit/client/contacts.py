"""Contacts read operations: search, get-by-id, and pagination.

Endpoints and the full contact schema come from the official OpenAPI spec
(``apps/contacts.json`` in github.com/GoHighLevel/highlevel-api-docs). The spec marks
``GET /contacts/`` deprecated; ``POST /contacts/search`` is the current list endpoint.
"""

from collections.abc import Iterator
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ghl_toolkit.client.http import GHLClient, iter_pages


class Contact(BaseModel):
    """A contact, curated to the fields documented in ``GetContectByIdSchema``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    first_name: str | None = None
    last_name: str | None = None
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    tags: list[str] = Field(default_factory=list)
    date_added: datetime | None = None
    date_updated: datetime | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    source: str | None = None
    assigned_to: str | None = None
    company_name: str | None = None
    location_id: str | None = None


# VERIFY: the POST /contacts/search 200 response has no schema in the official spec; the
# {"contacts": [...], "total": N} envelope is assumed, and item fields are parsed as
# optional so absence is safe. See VERIFY.md (V7).
class ContactPage(BaseModel):
    """One page of contact search results."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    contacts: list[Contact] = Field(default_factory=list)
    total: int | None = None


def search_contacts(client: GHLClient, *, limit: int = 20, page: int = 1) -> ContactPage:
    """Return one page of contacts for the configured location."""
    # VERIFY: the search request body schema is empty in the official spec; locationId,
    # page, and pageLimit are assumed from the deprecated list endpoint's parameter
    # vocabulary. See VERIFY.md (V6).
    body = {
        "locationId": client.settings.location_id,
        "page": page,
        "pageLimit": limit,
    }
    response = client.post("/contacts/search", json=body)
    return ContactPage.model_validate(response.json())


def get_contact(client: GHLClient, contact_id: str) -> Contact:
    """Return a single contact by id."""
    response = client.get(f"/contacts/{contact_id}")
    return Contact.model_validate(response.json()["contact"])


def iter_contacts(client: GHLClient, *, page_size: int = 20) -> Iterator[Contact]:
    """Yield every contact for the location, fetching pages as needed."""

    def fetch(cursor: int | None) -> tuple[list[Contact], int | None]:
        current_page = 1 if cursor is None else cursor
        result = search_contacts(client, limit=page_size, page=current_page)
        next_page = current_page + 1 if len(result.contacts) == page_size else None
        return result.contacts, next_page

    return iter_pages(fetch)
