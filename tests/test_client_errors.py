"""Typed error mapping for API responses."""

import httpx
import pytest
import respx

from ghl_toolkit.client import ApiError, AuthError, NotFound, RateLimited

BASE_URL = "https://api.test"


def test_401_raises_auth_error(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(
            return_value=httpx.Response(401, json=load_fixture("error_401.json"))
        )
        with pytest.raises(AuthError) as exc_info:
            client.get("/ping")

    assert exc_info.value.status_code == 401
    assert exc_info.value.message == "Invalid token"


def test_403_raises_auth_error(client):
    body = {"statusCode": 403, "message": "Forbidden resource", "error": "Forbidden"}
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(return_value=httpx.Response(403, json=body))
        with pytest.raises(AuthError) as exc_info:
            client.get("/ping")

    assert exc_info.value.status_code == 403


def test_404_raises_not_found(client):
    body = {"statusCode": 404, "message": "Location not found", "error": "Not Found"}
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(return_value=httpx.Response(404, json=body))
        with pytest.raises(NotFound) as exc_info:
            client.get("/ping")

    assert exc_info.value.status_code == 404


def test_400_raises_api_error_without_retry(client, sleeps):
    body = {"statusCode": 400, "message": "Bad request", "error": "Bad Request"}
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/ping").mock(return_value=httpx.Response(400, json=body))
        with pytest.raises(ApiError) as exc_info:
            client.get("/ping")

    assert exc_info.type is ApiError
    assert route.call_count == 1
    assert sleeps == []


def test_422_list_message_joined(client, load_fixture):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(
            return_value=httpx.Response(422, json=load_fixture("error_422_message_list.json"))
        )
        with pytest.raises(ApiError) as exc_info:
            client.get("/ping")

    assert exc_info.value.message == "email must be an email; phone must be a phone number"


def test_non_json_body_falls_back_to_text(client):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(return_value=httpx.Response(400, text="upstream exploded"))
        with pytest.raises(ApiError) as exc_info:
            client.get("/ping")

    assert exc_info.value.message == "upstream exploded"


def test_429_exhaustion_raises_rate_limited_with_retry_after(client):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(return_value=httpx.Response(429, headers={"Retry-After": "2"}))
        with pytest.raises(RateLimited) as exc_info:
            client.get("/ping")

    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_after == 2.0
