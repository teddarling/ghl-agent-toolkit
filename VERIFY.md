# VERIFY — unverified HighLevel API details

Facts the official docs (<https://highlevel.stoplight.io/docs/integrations/> and
<https://marketplace.gohighlevel.com/docs/>) do not confirm. Each entry has a matching
`# VERIFY:` marker at the code location that depends on the assumption. Remove an entry —
and its marker — once the detail is confirmed against the docs or observed API behavior.

## V1 — `Retry-After` on 429 responses

- **Unverified:** whether the API sends a `Retry-After` header when rate limiting.
- **Assumption:** honored with standard HTTP semantics when present; otherwise the client
  falls back to the documented `X-RateLimit-*` headers, then jittered backoff.
- **Marker:** `src/ghl_toolkit/client/http.py` (`retry_delay`).

## V2 — error response body shape

- **Unverified:** the official docs list error status codes but not body schemas. The shape
  `{"statusCode": ..., "message": <string | list>, "error": ...}` is observed in the wild only.
- **Assumption:** parse defensively — prefer `message` (lists joined with `"; "`), fall back
  to `error`, then to the raw response text.
- **Marker:** `src/ghl_toolkit/client/errors.py` (`_extract_message`).

## V3 — get-location response schema

- **Unverified:** the response schema for `GET /locations/:locationId` is not rendered in the
  docs. The `{"location": {...}}` envelope in `tests/fixtures/location_response.json` is
  representative, not doc-quoted.
- **Assumption:** read the envelope and its fields defensively; missing keys degrade to
  placeholders instead of crashing.
- **Marker:** `src/ghl_toolkit/cli.py` (`doctor`).

## V4 — Private Integration tokens and Marketplace-app rate limits

- **Unverified:** the rate-limit FAQ states 100 requests / 10s and 200,000/day per
  "Marketplace app"; whether Private Integration tokens share exactly those limits is implied
  but not stated.
- **Assumption:** the same limits apply.
- **Marker:** `src/ghl_toolkit/client/http.py` (module docstring).

## V5 — per-resource pagination parameters

- **Unverified:** pagination parameter conventions per resource (contacts, opportunities,
  conversations) — the resource doc pages did not render during verification.
- **Assumption:** none taken. Phase 2 ships a shape-agnostic cursor iterator; each Phase 3
  resource module must verify its own pagination parameters against the docs before use.
- **Marker:** `src/ghl_toolkit/client/http.py` (`iter_pages`).
