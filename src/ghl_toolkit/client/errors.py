"""Typed errors for HighLevel API responses."""

import httpx


class ApiError(Exception):
    """An API request failed with an error response."""

    def __init__(self, status_code: int, message: str, body: object, method: str, url: str):
        super().__init__(f"{method} {url} -> {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.body = body
        self.method = method
        self.url = url


class AuthError(ApiError):
    """The token was rejected (401) or lacks a required scope (403)."""


class NotFound(ApiError):
    """The requested resource does not exist (404)."""


class RateLimited(ApiError):
    """The request was rate limited (429)."""

    def __init__(
        self,
        status_code: int,
        message: str,
        body: object,
        method: str,
        url: str,
        retry_after: float | None = None,
    ):
        super().__init__(status_code, message, body, method, url)
        self.retry_after = retry_after


def parse_retry_after(value: str | None) -> float | None:
    """Parse a Retry-After header value given in seconds.

    The HTTP-date form is deliberately not handled; an unparseable value reads
    as absent so callers fall back to computed backoff.
    """
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _extract_message(response: httpx.Response) -> tuple[str, object]:
    # VERIFY: the error body shape {"statusCode", "message", "error"} is not documented in the
    # official API docs (only status codes are); parsing is defensive. See VERIFY.md (V2).
    try:
        body = response.json()
    except ValueError:
        text = response.text.strip()
        return text or response.reason_phrase, response.text
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, list):
            return "; ".join(str(part) for part in message), body
        if isinstance(message, str) and message:
            return message, body
        error = body.get("error")
        if isinstance(error, str) and error:
            return error, body
    return response.text, body


def raise_for_status(response: httpx.Response) -> httpx.Response:
    """Return the response if successful, else raise the matching typed error."""
    if response.status_code < 400:
        return response
    message, body = _extract_message(response)
    status = response.status_code
    method = response.request.method
    url = str(response.request.url)
    if status in (401, 403):
        raise AuthError(status, message, body, method, url)
    if status == 404:
        raise NotFound(status, message, body, method, url)
    if status == 429:
        retry_after = parse_retry_after(response.headers.get("Retry-After"))
        raise RateLimited(status, message, body, method, url, retry_after=retry_after)
    raise ApiError(status, message, body, method, url)
