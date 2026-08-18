"""HighLevel API client: HTTP transport, auth, typed errors, and read operations."""

from ghl_toolkit.client.auth import auth_headers
from ghl_toolkit.client.contacts import (
    Contact,
    ContactPage,
    get_contact,
    iter_contacts,
    search_contacts,
)
from ghl_toolkit.client.errors import ApiError, AuthError, NotFound, RateLimited
from ghl_toolkit.client.http import GHLClient

__all__ = [
    "ApiError",
    "AuthError",
    "Contact",
    "ContactPage",
    "GHLClient",
    "NotFound",
    "RateLimited",
    "auth_headers",
    "get_contact",
    "iter_contacts",
    "search_contacts",
]
