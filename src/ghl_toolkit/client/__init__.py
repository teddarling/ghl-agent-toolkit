"""HighLevel API client: HTTP transport, auth, and typed errors."""

from ghl_toolkit.client.auth import auth_headers
from ghl_toolkit.client.errors import ApiError, AuthError, NotFound, RateLimited

__all__ = [
    "ApiError",
    "AuthError",
    "NotFound",
    "RateLimited",
    "auth_headers",
]
