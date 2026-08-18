"""Wire-level behavior of the GHL HTTP client."""

import httpx
import pytest
import respx

from ghl_toolkit.client import GHLClient
from ghl_toolkit.settings import Settings

BASE_URL = "https://api.test"


def test_sends_auth_and_version_headers(client):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/ping").mock(return_value=httpx.Response(200, json={}))
        client.get("/ping")

    headers = route.calls.last.request.headers
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Version"] == "2021-07-28"
    assert headers["Accept"] == "application/json"
    assert headers["User-Agent"].startswith("ghl-toolkit/")


def test_base_url_comes_from_settings():
    settings = Settings(
        _env_file=None,
        api_token="test-token",
        location_id="loc_test123",
        api_base_url="https://alt.test",
    )
    with respx.mock(base_url="https://alt.test") as router:
        route = router.get("/ping").mock(return_value=httpx.Response(200, json={}))
        with GHLClient(settings) as ghl_client:
            ghl_client.get("/ping")

    assert str(route.calls.last.request.url) == "https://alt.test/ping"


def test_context_manager_closes_client(settings):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(return_value=httpx.Response(200, json={}))
        with GHLClient(settings) as ghl_client:
            ghl_client.get("/ping")
        with pytest.raises(RuntimeError):
            ghl_client.get("/ping")
