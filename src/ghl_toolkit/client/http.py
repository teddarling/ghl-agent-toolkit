"""HTTP transport for the HighLevel API: retries, backoff, and rate-limit handling.

Rate limits for Private Integration tokens are documented as 100 requests per
10 seconds (burst) and 200,000 per day:
https://marketplace.gohighlevel.com/docs/oauth/Faqs/index.html
"""

# VERIFY: the rate-limit FAQ states limits per "Marketplace app"; whether Private
# Integration tokens share exactly those limits is assumed, not stated. See VERIFY.md (V4).

import importlib.metadata
import random
import time
from collections.abc import Callable, Iterator, Mapping
from contextlib import suppress
from types import TracebackType

import httpx

from ghl_toolkit.client.auth import auth_headers
from ghl_toolkit.client.errors import parse_retry_after, raise_for_status
from ghl_toolkit.settings import Settings, get_settings

MAX_ATTEMPTS = 5
BASE_DELAY = 0.5
MAX_DELAY = 30.0
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})


def should_retry(method: str, status_code: int, attempt: int) -> bool:
    """Whether a failed response may be retried.

    429 is always retryable: a rate-limited request was never processed. 5xx is
    retryable only for methods that are safe to replay; a POST that returned
    5xx may already have been applied server-side.
    """
    if attempt >= MAX_ATTEMPTS - 1:
        return False
    if status_code == 429:
        return True
    return status_code in RETRYABLE_STATUSES and method.upper() != "POST"


def retry_delay(attempt: int, headers: Mapping[str, str], rng: random.Random) -> float:
    """Seconds to wait before the next attempt.

    Precedence: Retry-After, then the documented rate-limit interval when the
    window is exhausted, then full jitter capped at MAX_DELAY.
    """
    # VERIFY: Retry-After on 429 is not documented for the HighLevel API; it is honored
    # with standard semantics when present. See VERIFY.md (V1).
    retry_after = parse_retry_after(headers.get("Retry-After"))
    if retry_after is not None:
        return retry_after
    if headers.get("X-RateLimit-Remaining") == "0":
        interval_ms = headers.get("X-RateLimit-Interval-Milliseconds")
        if interval_ms is not None:
            with suppress(ValueError):
                return float(interval_ms) / 1000.0
    return rng.uniform(0.0, min(MAX_DELAY, BASE_DELAY * 2**attempt))


def iter_pages[T, C](fetch: Callable[[C | None], tuple[list[T], C | None]]) -> Iterator[T]:
    """Yield items across every page of a cursor-paginated endpoint.

    ``fetch`` receives the previous page's cursor (``None`` on the first call) and
    returns ``(items, next_cursor)``; iteration stops when the next cursor is ``None``.
    """
    cursor: C | None = None
    while True:
        items, cursor = fetch(cursor)
        yield from items
        if cursor is None:
            return


class GHLClient:
    """Synchronous HighLevel API client with retry and rate-limit handling.

    ``sleep`` and ``rng`` exist so tests can observe backoff decisions without
    waiting on real time; production callers keep the defaults.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        timeout: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._settings = settings if settings is not None else get_settings()
        self._sleep = sleep
        self._rng = rng if rng is not None else random.Random()
        headers = auth_headers(self._settings)
        headers["User-Agent"] = f"ghl-toolkit/{importlib.metadata.version('ghl-toolkit')}"
        self._client = httpx.Client(
            base_url=self._settings.api_base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    @property
    def settings(self) -> Settings:
        """The settings this client was constructed with."""
        return self._settings

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        json: object | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Send a request, retrying per the module's backoff policy, and return the response.

        ``headers`` are merged over the client defaults — some endpoints pin a
        different ``Version`` than the client-wide 2021-07-28.

        Raises the matching typed error from :mod:`ghl_toolkit.client.errors` when the
        final response is an error, or the transport error when the connection fails.
        """
        attempt = 0
        while True:
            hint_headers: Mapping[str, str] = {}
            try:
                response = self._client.request(
                    method, path, params=params, json=json, headers=headers
                )
            except httpx.TransportError:
                if method.upper() == "POST" or attempt >= MAX_ATTEMPTS - 1:
                    raise
            else:
                if response.status_code < 400:
                    return response
                if not should_retry(method, response.status_code, attempt):
                    raise_for_status(response)
                if response.status_code == 429:
                    hint_headers = response.headers
            self._sleep(retry_delay(attempt, hint_headers, self._rng))
            attempt += 1

    def get(
        self,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        return self.request("GET", path, params=params, headers=headers)

    def post(
        self,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        json: object | None = None,
    ) -> httpx.Response:
        return self.request("POST", path, params=params, json=json)

    def put(
        self,
        path: str,
        *,
        params: Mapping[str, object] | None = None,
        json: object | None = None,
    ) -> httpx.Response:
        return self.request("PUT", path, params=params, json=json)

    def delete(self, path: str, *, params: Mapping[str, object] | None = None) -> httpx.Response:
        return self.request("DELETE", path, params=params)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GHLClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()
