"""Retry, backoff, and rate-limit handling."""

import random

import httpx
import pytest
import respx

from ghl_toolkit.client import ApiError, RateLimited

BASE_URL = "https://api.test"


def test_429_then_success_retries(client, sleeps):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/ping").mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json={"ok": True})]
        )
        response = client.get("/ping")

    assert response.status_code == 200
    assert route.call_count == 2
    assert len(sleeps) == 1


def test_retry_after_header_honored(client, sleeps):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "3"}),
                httpx.Response(200, json={}),
            ]
        )
        client.get("/ping")

    assert sleeps == [3.0]


def test_rate_limit_interval_fallback(client, sleeps):
    headers = {"X-RateLimit-Remaining": "0", "X-RateLimit-Interval-Milliseconds": "10000"}
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(
            side_effect=[httpx.Response(429, headers=headers), httpx.Response(200, json={})]
        )
        client.get("/ping")

    assert sleeps == [10.0]


def test_jitter_backoff_sequence(client, sleeps):
    with respx.mock(base_url=BASE_URL) as router:
        router.get("/ping").mock(return_value=httpx.Response(429))
        with pytest.raises(RateLimited):
            client.get("/ping")

    expected_rng = random.Random(42)
    expected = [expected_rng.uniform(0.0, min(30.0, 0.5 * 2**attempt)) for attempt in range(4)]
    assert sleeps == expected
    assert all(delay <= 30.0 for delay in sleeps)


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_5xx_then_success_retries(client, status):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/ping").mock(
            side_effect=[httpx.Response(status), httpx.Response(200, json={})]
        )
        response = client.get("/ping")

    assert response.status_code == 200
    assert route.call_count == 2


def test_5xx_exhaustion(client, sleeps):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/ping").mock(return_value=httpx.Response(500))
        with pytest.raises(ApiError):
            client.get("/ping")

    assert route.call_count == 5
    assert len(sleeps) == 4


def test_post_500_not_retried(client, sleeps):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/ping").mock(return_value=httpx.Response(500))
        with pytest.raises(ApiError):
            client.post("/ping", json={"name": "x"})

    assert route.call_count == 1
    assert sleeps == []


def test_post_429_retried(client, sleeps):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/ping").mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json={})]
        )
        response = client.post("/ping", json={"name": "x"})

    assert response.status_code == 200
    assert route.call_count == 2


def test_get_transport_error_retried(client):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.get("/ping").mock(
            side_effect=[httpx.ConnectError("connection refused"), httpx.Response(200, json={})]
        )
        response = client.get("/ping")

    assert response.status_code == 200
    assert route.call_count == 2


def test_post_transport_error_not_retried(client, sleeps):
    with respx.mock(base_url=BASE_URL) as router:
        route = router.post("/ping").mock(side_effect=httpx.ConnectError("connection refused"))
        with pytest.raises(httpx.ConnectError):
            client.post("/ping", json={"name": "x"})

    assert route.call_count == 1
    assert sleeps == []
