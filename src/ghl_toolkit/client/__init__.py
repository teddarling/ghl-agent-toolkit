"""HighLevel API client: HTTP transport, auth, and typed errors."""

from ghl_toolkit.client.auth import auth_headers
from ghl_toolkit.client.errors import ApiError, AuthError, NotFound, RateLimited
from ghl_toolkit.client.http import GHLClient

__all__ = [
    "ApiError",
    "AuthError",
    "GHLClient",
    "NotFound",
    "RateLimited",
    "auth_headers",
]
