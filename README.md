# ghl-agent-toolkit

[![CI](https://github.com/teddarling/ghl-agent-toolkit/actions/workflows/ci.yml/badge.svg)](https://github.com/teddarling/ghl-agent-toolkit/actions/workflows/ci.yml)
[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/teddarling/ghl-agent-toolkit)

**Production patterns for putting AI agents to work inside GoHighLevel — safely.**

Most GHL + AI examples are demos: happy path, no rate limiting, writes straight to your CRM with no way to review what the AI did. This toolkit is the opposite. It's the harness I use in my own business, extracted and open-sourced: a hardened Python client for the HighLevel API, a small set of useful agents on top of it, and a safety model where **the agent proposes and a human approves** before anything touches your data.

> Models are commodities. The harness is what you own.

## What's inside

- **A production-grade GHL API client** — token auth, automatic retry with backoff, rate-limit awareness, pagination handling, and typed responses. The boring parts done right, because the boring parts are what break at 2am.
- **Agents that do real CRM work:**
  - `lead-tagger` — reads new inbound contacts and proposes tags based on your rules
  - `reply-drafter` — drafts responses to inbound conversations for human review (it never sends on its own)
  - `lead-scorer` — scores leads and writes the result to a custom field
- **A CLI (`ghl`)** — inspect contacts, opportunities, and conversations from your terminal; run any agent in `--dry-run` mode and see exactly what it *would* change before letting it.
- **A FastAPI webhook receiver** — the event-driven entry point: contact created → agent proposes → you approve → toolkit applies.
- **A React approval dashboard** — the human side of the loop: see every pending proposal, the diff of what the agent wants to change and why, and approve or reject in one click.
- **An audit log** — every write the toolkit makes to your GHL account is recorded: what changed, which agent proposed it, who approved it.

## The safety model

Every agent action goes through three stages:

```
PROPOSE  →  the agent reads data and produces a proposed change (never a direct write)
APPROVE  →  a human reviews it (CLI prompt, or auto-approve rules you opt into per action type)
APPLY    →  the toolkit executes the change, records it in the audit log
```

Dry-run is the default. You have to explicitly turn on writes. This is not paranoia — it's what it takes to let an AI touch a CRM that runs a real business.

## Quickstart

No GHL account or API keys? Take the tour on seeded demo data first:

```bash
uv sync
GHL_DEMO_MODE=1 uv run ghl contacts list
GHL_DEMO_MODE=1 uv run ghl agent tag --dry-run   # the full propose flow, zero writes
```

Or run the whole thing — server, seeded proposals, and the approval dashboard —
with one command: `docker compose up`, then open <http://localhost:8000>.

Against your own GoHighLevel account:

```bash
uv sync
cp .env.example .env        # add your HighLevel Private Integration token + location ID
uv run ghl doctor           # verifies auth, location access, and rate limits
uv run ghl contacts list --limit 5
uv run ghl agent tag --dry-run   # see what the lead-tagger would do, changes applied: none
```

## Repo structure

```
ghl-agent-toolkit/
├── src/ghl_toolkit/
│   ├── client/            # HighLevel API client
│   │   ├── auth.py        # token handling (Private Integration / OAuth)
│   │   ├── http.py        # retries, backoff, rate-limit handling
│   │   ├── contacts.py
│   │   ├── opportunities.py
│   │   ├── conversations.py
│   │   └── custom_fields.py
│   ├── agents/
│   │   ├── harness.py     # propose/approve/apply, cost budget, structured outputs, tracing
│   │   ├── lead_tagger.py
│   │   ├── reply_drafter.py
│   │   └── lead_scorer.py
│   ├── llm.py             # provider-thin LLM layer (Anthropic first, swappable)
│   ├── proposals.py       # persistent proposal queue (webhook → approval)
│   ├── demo.py            # demo mode: seeded data, no credentials needed
│   ├── audit.py           # audit log for every write
│   └── cli.py             # Typer CLI
├── server/
│   └── main.py            # FastAPI webhook receiver + proposals API
├── web/                   # React (Vite + TypeScript) approval dashboard
│   └── src/
├── tests/                 # unit tests against mocked API responses — no live calls
├── examples/              # runnable end-to-end examples
└── docs/
    ├── production-notes.md   # rate limits, idempotency, retry strategy, token scopes
    └── agent-safety.md       # the propose/approve/apply model in depth
```

## What this is not

- Not an MCP server — HighLevel ships an official one. This is the production layer for building your *own* automations and agents against the API.
- Not a chatbot builder. GHL has Conversation AI. This is for the work around and beyond it: tagging, scoring, drafting, syncing — with review.
- Not a demo. If a pattern in here wouldn't survive a real client account, it doesn't ship.

## Status

Everything described above ships and is tested: the client core (retry,
backoff, rate-limit handling), the CLI read operations, all three agents
behind the propose → approve → apply gate, the webhook receiver and proposals
API, the React approval dashboard, the audit log, and a credential-free demo
mode. API details the official docs don't confirm are tracked honestly in
[VERIFY.md](VERIFY.md) rather than guessed — the webhook payload items there
are the first thing to check before pointing real traffic at the receiver.
PRs welcome — especially real-world failure stories.

## About

Built by [Ted Darling](https://github.com/teddarling) — 28 years of full-stack development, the last several building and running production AI systems. I run this toolkit against my own GoHighLevel account. If you have a GHL + AI build that needs to survive real customers, that's the work I do.

Apache 2.0.