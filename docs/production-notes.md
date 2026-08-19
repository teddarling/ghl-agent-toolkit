# Production notes

What it takes to run this against a real GoHighLevel account: the rate-limit and
retry behavior built into the client, the token scopes each command needs, the
cost controls on the LLM layer, and deployment options. Everything below
describes code that exists in this repo — file references point at the
implementation.

## Rate limits

HighLevel documents 100 requests per 10 seconds (burst) and 200,000 per day.
The client (`src/ghl_toolkit/client/http.py`) reads the API's own rate-limit
headers rather than guessing:

| Header | Used for |
| --- | --- |
| `X-RateLimit-Limit-Daily` | reported by `ghl doctor` |
| `X-RateLimit-Daily-Remaining` | reported by `ghl doctor` |
| `X-RateLimit-Interval-Milliseconds` | backoff delay when the window is exhausted |
| `X-RateLimit-Max` | reported by `ghl doctor` |
| `X-RateLimit-Remaining` | `0` triggers the interval-based delay |

Whether Private Integration tokens share exactly the documented Marketplace-app
limits is not stated in the docs — see [VERIFY.md](../VERIFY.md) (V4).

## Retry policy

Implemented in `GHLClient.request` with pure, unit-tested helpers
(`should_retry`, `retry_delay`):

| Aspect | Policy |
| --- | --- |
| Retryable statuses | 429, 500, 502, 503, 504 |
| Attempts | 5 total (initial + 4 retries) |
| Delay precedence on 429 | `Retry-After` → `X-RateLimit-Interval-Milliseconds` (when remaining is 0) → full jitter |
| Jitter | `uniform(0, min(30s, 0.5s × 2^attempt))` |
| POST idempotency stance | POST retries **only** on 429 — a rate-limited request was never processed, but a 5xx POST may already have been applied server-side. Transport errors likewise never retry a POST. |

Every path in that table has a test in `tests/test_client_retry.py`.

## Token scopes per command

Grant these on the Private Integration (Settings → Private Integrations);
`ghl doctor` verifies the first by probing and reports that scopes cannot be
introspected via any documented API:

| Command | Scopes |
| --- | --- |
| `ghl doctor` | `locations.readonly` |
| `ghl contacts list` / `get` | `contacts.readonly` |
| `ghl opps list` | `opportunities.readonly` |
| `ghl convos list` | `conversations.readonly` |
| `ghl agent tag` | `contacts.readonly` (+ `contacts.write` for `--apply`) |
| `ghl agent draft` | `conversations.readonly`, `conversations/message.readonly` |
| `ghl agent score` | `contacts.readonly`, `locations/customFields.readonly` (+ `contacts.write` for `--apply`) |

Note the messages endpoint pins `Version: 2021-04-15` — a different API version
than every other call. The client handles this per-request
(`src/ghl_toolkit/client/conversations.py`).

## LLM cost controls

The provider-thin layer (`src/ghl_toolkit/llm.py`) enforces a per-run USD
budget (`GHL_AGENT_BUDGET_USD`, default $1.00) as a pre-call hard stop:
once spent ≥ limit, the next call raises before the provider is invoked.
Malformed-output retries and refusals both charge real usage. Every attempt —
including failures — writes a JSONL trace line (`GHL_LLM_TRACE_PATH`) with
prompts, response, tokens, and cost. Pricing is a source-commented table that
refuses unknown models rather than guessing a rate.

## State files

All three are append-only JSONL, path-configurable, and gitignored:

- `audit.log.jsonl` (`GHL_AUDIT_LOG_PATH`) — one entry per applied write.
- `llm-trace.jsonl` (`GHL_LLM_TRACE_PATH`) — one entry per LLM call attempt.
- `proposals.jsonl` (`GHL_PROPOSALS_PATH`) — the webhook server's proposal
  queue; last record per id wins on reload, so restarts are crash-safe.

## Deployment

The server carries no authentication on the proposals API by design — run it
bound to localhost (the dashboard dev-proxies to it) or behind your own
gateway. The one-command demo is `docker compose up` (multi-stage build:
dashboard compiled, served by the FastAPI app at `/`).

For a real deployment, the same patterns discussed for this repo apply: a
small always-on box (Hetzner-class VPS, Fly.io machine with a volume) or a
home machine behind Cloudflare Tunnel — the JSONL state files want a
persistent disk, and the webhook endpoint wants to stay warm. Put Cloudflare
Access or a VPN in front of everything except the webhook route.

## Ecosystem watch: httpx → httpx2

Upstream `httpx` has gone quiet; the ecosystem is moving to Pydantic's
maintained `httpx2` fork. This repo already uses `httpx2` as a dev dependency
(Starlette's TestClient prefers it), while the production client, respx test
strategy, and the anthropic SDK remain on `httpx`. Migrating the client is
deliberate future work — it touches the retry engine and the entire offline
test strategy — not a dependency bump to do casually.

## Unverified API details

Anything the official docs don't confirm is marked `# VERIFY:` in code and
listed in [VERIFY.md](../VERIFY.md) with the assumption taken. Ten items are
open at the time of writing; the webhook-shape items (V9/V10) are the ones to
resolve first if you run the server against real traffic — see
[agent-safety.md](agent-safety.md).
