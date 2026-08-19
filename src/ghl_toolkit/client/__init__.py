"""HighLevel API client: HTTP transport, auth, typed errors, and read operations."""

from ghl_toolkit.client.auth import auth_headers
from ghl_toolkit.client.contacts import (
    Contact,
    ContactPage,
    add_contact_tags,
    get_contact,
    iter_contacts,
    search_contacts,
)
from ghl_toolkit.client.conversations import (
    Conversation,
    ConversationPage,
    Message,
    MessagePage,
    fetch_messages,
    search_conversations,
)
from ghl_toolkit.client.errors import ApiError, AuthError, NotFound, RateLimited
from ghl_toolkit.client.http import GHLClient
from ghl_toolkit.client.opportunities import (
    Opportunity,
    OpportunityMeta,
    OpportunityPage,
    iter_opportunities,
    search_opportunities,
)

__all__ = [
    "ApiError",
    "AuthError",
    "Contact",
    "ContactPage",
    "Conversation",
    "ConversationPage",
    "GHLClient",
    "Message",
    "MessagePage",
    "NotFound",
    "Opportunity",
    "OpportunityMeta",
    "OpportunityPage",
    "RateLimited",
    "add_contact_tags",
    "auth_headers",
    "fetch_messages",
    "get_contact",
    "iter_contacts",
    "iter_opportunities",
    "search_contacts",
    "search_conversations",
    "search_opportunities",
]
