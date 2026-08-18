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

## V6 — `POST /contacts/search` request body

- **Unverified:** the official OpenAPI spec (`apps/contacts.json` in
  github.com/GoHighLevel/highlevel-api-docs) defines the search body as an empty object
  (`SearchBodyV2DTO` has no properties), and the official Python SDK generates the same
  empty class. The full filter/sort vocabulary is documented only in a JS-rendered page
  the spec links to.
- **Assumption:** send only `{"locationId", "page", "pageLimit"}`, taken from the
  deprecated `GET /contacts/` endpoint's parameter vocabulary. No filters or sort.
- **Marker:** `src/ghl_toolkit/client/contacts.py` (`search_contacts`).

## V7 — `POST /contacts/search` response envelope

- **Unverified:** the spec declares no schema for the 200 response. The documented
  search-item schema (`ContactsSearchSchema`) also omits display fields (name, phone)
  that the full contact schema has.
- **Assumption:** a `{"contacts": [...], "total": N}` envelope whose items are in
  practice a superset of `ContactsSearchSchema`; all item fields parse as optional so
  absence is safe.
- **Marker:** `src/ghl_toolkit/client/contacts.py` (`ContactPage`).

## V8 — conversations deep pagination

- **Unverified:** `GET /conversations/search` documents a `startAfterDate` cursor that
  "should contain the sort value of the last document", but no documented field on
  `ConversationSchema` items carries that value.
- **Assumption:** none taken — the toolkit ships single-page `search_conversations`
  only, with no iterator, rather than fabricate a cursor source.
- **Marker:** `src/ghl_toolkit/client/conversations.py` (module comment).

## V9 — webhook channel applicability and signatures

- **Unverified:** the Webhook Integration Guide documents signed webhooks (current:
  Ed25519 via `X-GHL-Signature`, legacy: RSA via `X-WH-Signature`, both public keys
  published) for **Marketplace apps**. Whether a Private-Integration-only setup can
  subscribe to that signed channel is not documented, and sub-account workflow
  "custom webhook" actions POST unsigned, user-shaped payloads.
- **Assumption:** signature verification (Ed25519 only — RSA is officially labeled
  legacy and is deliberately not implemented) is opt-in via
  `GHL_WEBHOOK_VERIFY_SIGNATURE`; an optional `GHL_WEBHOOK_SHARED_SECRET` header check
  is the defense for unsigned channels. A forged webhook can only create a pending
  proposal a human must approve.
- **Marker:** `server/main.py` (`_check_webhook_auth`).

## V10 — webhook envelope fields

- **Unverified:** the integration guide's overview mentions `timestamp`/`webhookId`
  envelope fields; the official ContactCreate example
  (`docs/webhook events/ContactCreate.md` in github.com/GoHighLevel/highlevel-api-docs)
  shows a flat payload with neither.
- **Assumption:** only `type`, `id`, and `locationId` are required; unknown fields are
  tolerated. Dedup keys on `(action, target_id)` against pending proposals, not on the
  unverifiable `webhookId`.
- **Marker:** `server/main.py` (`_parse_event`).

## Resolved

### V5 — per-resource pagination parameters (resolved in Phase 3)

Verified from the official OpenAPI specs in github.com/GoHighLevel/highlevel-api-docs:
opportunities page via the `startAfter`/`startAfterId` cursor echoed in `meta`
(`apps/opportunities.json`); conversations expose `limit` and a `startAfterDate` cursor
(`apps/conversations.json` — but see V8); contacts page mechanics are covered by V6/V7.
