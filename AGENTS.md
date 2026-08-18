# AGENTS.md

*Canonical instructions for any coding agent (Claude Code, Codex, or others) working in this repo. CLAUDE.md points here — edit this file only.*

## What this project is

ghl-agent-toolkit is production patterns for putting AI agents to work inside GoHighLevel — safely. It has three parts: a hardened Python client for the HighLevel API, a small set of agents on top of it, and a propose → approve → apply safety model where a human approves before anything touches CRM data. This is a public portfolio repo whose positioning is "production-grade, not demos" — the code quality IS the product. No placeholder code, no TODO stubs, no fabricated API behavior; if a pattern wouldn't survive a real client account, it doesn't ship.

> Models are commodities. The harness is what you own.

## Commands

Everything Python runs through uv — never invoke pip or python directly. Commands become available at the phase noted; do not document a command here until it actually works.

### Python (from Phase 1)

| Command | Purpose |
| --- | --- |
| `uv sync` | Install/sync all dependencies from uv.lock |
| `uv run pytest` | Run the full test suite (offline; must pass before every commit) |
| `uv run ruff check .` | Lint |
| `uv run ruff format --check .` | Formatting check (drop `--check` to fix) |
| `uv run ghl --help` | CLI entry point (from Phase 1) |
| `uv run ghl doctor` | Verify auth + token scopes (from Phase 2) |
| `uv run uvicorn server.main:app` | Webhook receiver (from Phase 5) |

### Web dashboard (from Phase 6)

| Command | Purpose |
| --- | --- |
| `pnpm dev` (in `web/`) | Vite dev server, proxies to the FastAPI server (from Phase 6) |
| `pnpm test` (in `web/`) | Vitest component tests (from Phase 6) |
| `pnpm build` (in `web/`) | Production build + typecheck (from Phase 6) |

## Non-negotiables

- **uv only.** Python 3.12, src layout, `.python-version` pinned. Add dependencies with `uv add`, never pip. `uv.lock` is committed. Everything runs via `uv run`.
- **No secrets anywhere.** Config comes from environment variables via the pydantic-settings module (`src/ghl_toolkit/settings.py` once it exists). `.env` is gitignored; `.env.example` documents every variable. Never commit tokens, even in fixtures or docs.
- **All tests run offline.** HTTP is mocked with respx; realistic response fixtures live in `tests/fixtures/`. Never call the live HighLevel API from tests. The client's retry/rate-limit logic is the point of the repo — cover it meaningfully.
- **Writes are gated.** Every agent follows propose → approve → apply. Dry-run is the default everywhere; applying requires an explicit `--apply` flag. Every applied change writes a structured JSONL entry to the audit log.
- **Never invent HighLevel API details.** Endpoints, auth headers, and payload shapes come from the official docs: <https://highlevel.stoplight.io/docs/integrations/> and <https://marketplace.gohighlevel.com/docs/>. Auth is a Private Integration token (Bearer) plus the `Version: 2021-07-28` header, confirmed per endpoint. Mark anything unverifiable with `# VERIFY:` in code and list it in `VERIFY.md` at the repo root — never guess silently.
- **Conventional commits.** `feat:`, `fix:`, `test:`, `docs:`, `chore:`, `ci:`. Small commits; commit at minimum at the end of each phase, and update the Phase status checklist below in the same commit that completes a phase.
- **README is the spec.** Match its repo structure exactly; if implementation forces a deviation, update the README in the same commit and say why.

## Phase status

Update this checklist in the same commit that completes a phase.

- [x] **Phase 0 — Agent context files** — complete (AGENTS.md, CLAUDE.md)
- [ ] **Phase 1 — Scaffold** — not started (uv init src layout, settings, .env.example, .gitignore, ruff, CI, green empty test tree, `ghl --help`)
- [ ] **Phase 2 — Client core** — not started (http client: retry/backoff/jitter, rate-limit headers, pagination, typed errors; `ghl doctor`)
- [ ] **Phase 3 — Read operations** — not started (contacts/opportunities/conversations, pydantic models, rich CLI tables)
- [ ] **Phase 4 — Harness + lead_tagger** — not started (propose/approve/apply, cost budget, structured outputs, tracing, audit log; `ghl agent tag`)
- [ ] **Phase 5 — Webhook receiver** — not started (FastAPI server/, proposals API, runnable example)
- [ ] **Phase 6 — React approval dashboard** — not started (web/, Vite + React + TS, TanStack Query, Vitest)
- [ ] **Phase 7 — Remaining agents + docs** — not started (reply_drafter, lead_scorer, docs/, final README pass)

## Known deviations from README

- README Quickstart says `pip install -e .` — conflicts with the uv-only rule. The Quickstart will be rewritten to uv commands in the Phase 7 final README pass, or in the same commit as any earlier README edit, whichever comes first. Until then, do not copy the pip command anywhere.

When this list is empty, keep the heading with "None currently."
