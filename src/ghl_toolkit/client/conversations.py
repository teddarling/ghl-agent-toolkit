"""Conversations read operations: single-page search and per-conversation messages.

Endpoints, parameters, and schemas come from the official OpenAPI spec
(``apps/conversations.json`` in github.com/GoHighLevel/highlevel-api-docs):
``GET /conversations/search`` with camelCase ``locationId`` and ``limit``, and
``GET /conversations/{conversationId}/messages`` (scope
``conversations/message.readonly``). Both endpoints pin their ``Version``
header to the enum value ``2021-04-15`` — not the client-wide 2021-07-28 —
so every request in this module sends the pinned value.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ghl_toolkit.client.http import GHLClient

MESSAGES_API_VERSION = "2021-04-15"

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
    response = client.get(
        "/conversations/search",
        params=params,
        headers={"Version": MESSAGES_API_VERSION},
    )
    return ConversationPage.model_validate(response.json())


class Message(BaseModel):
    """One message, curated to fields from ``GetMessageResponseDto``."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    id: str
    type: int | None = None
    message_type: str | None = None
    location_id: str | None = None
    contact_id: str | None = None
    conversation_id: str | None = None
    date_added: datetime | None = None
    direction: str | None = None
    body: str | None = None
    status: str | None = None
    content_type: str | None = None


class MessagePage(BaseModel):
    """The ``GetMessagesByConversationResponseDto`` envelope."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="ignore")

    messages: list[Message] = Field(default_factory=list)
    last_message_id: str | None = None
    next_page: bool | None = None


def fetch_messages(client: GHLClient, conversation_id: str, *, limit: int = 20) -> MessagePage:
    """Return one page of a conversation's messages (scope conversations/message.readonly)."""
    response = client.get(
        f"/conversations/{conversation_id}/messages",
        params={"limit": limit},
        headers={"Version": MESSAGES_API_VERSION},
    )
    return MessagePage.model_validate(response.json())
