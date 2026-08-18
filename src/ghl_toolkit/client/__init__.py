"""HighLevel API client: HTTP transport, auth, typed errors, and read operations."""

from ghl_toolkit.client.auth import auth_headers
from ghl_toolkit.client.contacts import (
    Contact,
    ContactPage,
    get_contact,
    iter_contacts,
    search_contacts,
)
from ghl_toolkit.client.conversations import (
    Conversation,
    ConversationPage,
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
    "NotFound",
    "Opportunity",
    "OpportunityMeta",
    "OpportunityPage",
    "RateLimited",
    "auth_headers",
    "get_contact",
    "iter_contacts",
    "iter_opportunities",
    "search_contacts",
    "search_conversations",
    "search_opportunities",
]
