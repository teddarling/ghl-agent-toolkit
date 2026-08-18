"""Opportunities read operations: search and cursor pagination.

Endpoint, parameters, and schemas come from the official OpenAPI spec
(``apps/opportunities.json`` in github.com/GoHighLevel/highlevel-api-docs):
``GET /opportunities/search`` takes a snake_case ``location_id``, ``limit`` (max 100),
and pages via the ``startAfter``/``startAfterId`` cursor echoed in ``meta``.
"""

from collections.abc import Iterator
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ghl_toolkit.client.http import GHLClient, iter_pages


class Opportunity(BaseModel):
    """An opportunity, curated to fields from ``SearchOpportunitiesResponseSchema``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    name: str | None = None
    status: str | None = None
    monetary_value: float | None = None
    pipeline_id: str | None = None
    pipeline_stage_id: str | None = None
    contact_id: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_status_change_at: datetime | None = None
    location_id: str | None = None
    source: str | None = None


class OpportunityMeta(BaseModel):
    """Pagination metadata from ``SearchSuccessfulResponseDto.meta``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    total: int | None = None
    start_after: int | None = None
    start_after_id: str | None = None
    current_page: int | None = None
    next_page: int | None = None


class OpportunityPage(BaseModel):
    """One page of opportunity search results."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    opportunities: list[Opportunity] = Field(default_factory=list)
    meta: OpportunityMeta | None = None


def search_opportunities(
    client: GHLClient,
    *,
    limit: int = 20,
    page: int = 1,
    start_after: int | None = None,
    start_after_id: str | None = None,
) -> OpportunityPage:
    """Return one page of opportunities for the configured location.

    When the ``startAfter``/``startAfterId`` cursor is given, ``page`` is omitted from
    the query — the spec's own ``nextPageUrl`` example pages by cursor alone.
    """
    params: dict[str, object] = {
        "location_id": client.settings.location_id,
        "limit": limit,
    }
    if start_after is not None or start_after_id is not None:
        if start_after is not None:
            params["startAfter"] = start_after
        if start_after_id is not None:
            params["startAfterId"] = start_after_id
    else:
        params["page"] = page
    response = client.get("/opportunities/search", params=params)
    return OpportunityPage.model_validate(response.json())


def iter_opportunities(client: GHLClient, *, page_size: int = 20) -> Iterator[Opportunity]:
    """Yield every opportunity for the location, following the meta cursor."""

    def fetch(cursor: tuple[int, str] | None) -> tuple[list[Opportunity], tuple[int, str] | None]:
        if cursor is None:
            result = search_opportunities(client, limit=page_size)
        else:
            start_after, start_after_id = cursor
            result = search_opportunities(
                client,
                limit=page_size,
                start_after=start_after,
                start_after_id=start_after_id,
            )
        meta = result.meta
        next_cursor = None
        if (
            meta is not None
            and meta.next_page is not None
            and meta.start_after is not None
            and meta.start_after_id is not None
        ):
            next_cursor = (meta.start_after, meta.start_after_id)
        return result.opportunities, next_cursor

    return iter_pages(fetch)
