"""Authentication headers for HighLevel API requests."""

from ghl_toolkit.settings import Settings

API_VERSION = "2021-07-28"


def auth_headers(settings: Settings) -> dict[str, str]:
    """Headers required on every request: Bearer token plus the pinned API version.

    Verified against the Private Integrations docs:
    https://marketplace.gohighlevel.com/docs/Authorization/PrivateIntegrationsToken/
    """
    return {
        "Authorization": f"Bearer {settings.api_token.get_secret_value()}",
        "Version": API_VERSION,
        "Accept": "application/json",
    }
