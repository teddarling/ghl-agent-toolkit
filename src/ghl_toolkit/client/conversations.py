"""Conversations read operations: single-page search.

Endpoint, parameters, and schemas come from the official OpenAPI spec
(``apps/conversations.json`` in github.com/GoHighLevel/highlevel-api-docs):
``GET /conversations/search`` with camelCase ``locationId`` and ``limit``.
"""

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ghl_toolkit.client.http import GHLClient

# VERIFY: no iterator is provided for conversations. The spec documents a
# ``startAfterDate`` cursor described as "the sort value of the last document", but no
# documented field on ConversationSchema items carries that value, so deep pagination
# cannot be built honestly. See VERIFY.md (V8).


class Conversation(BaseModel):
    """A conversation, curated to fields from ``ConversationSchema``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    contact_id: str | None = None
    contact_name: str | None = None
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    last_message_body: str | None = None
    last_message_type: str | None = None
    type: str | None = None
    unread_count: int | None = None
    location_id: str | None = None


class ConversationPage(BaseModel):
    """One page of conversation search results; ``total`` is required by the spec."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    conversations: list[Conversation] = Field(default_factory=list)
    total: int


def search_conversations(client: GHLClient, *, limit: int = 20) -> ConversationPage:
    """Return one page of recent conversations for the configured location."""
    params = {"locationId": client.settings.location_id, "limit": limit}
    response = client.get("/conversations/search", params=params)
    return ConversationPage.model_validate(response.json())
