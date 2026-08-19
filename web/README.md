# Approval dashboard

React (Vite + TypeScript) SPA for reviewing agent proposals: see every pending
proposal with its before/after diff and reasoning, then approve or reject.
Approved items show their audit-log entry.

## Run it (demo mode — no GHL account needed)

Two terminals from the repo root:

```bash
GHL_DEMO_MODE=1 uv run uvicorn server.main:app   # API on :8000, seeded proposals
```

```bash
cd web && pnpm install && pnpm dev               # dashboard on :5173
```

Open http://localhost:5173 — seeded proposals appear, and approving one works
fully offline (the demo server applies against a mock transport and writes a
real audit entry).

Against a real account, start the server without `GHL_DEMO_MODE` and with a
configured `.env` instead. The Vite dev server proxies `/proposals`,
`/webhooks`, `/healthz`, and `/audit` to `localhost:8000`, so there is no CORS
setup on either side.

## Commands

| Command | Purpose |
| --- | --- |
| `pnpm dev` | Vite dev server with API proxy |
| `pnpm build` | Typecheck (`tsc -b`) + production build |
| `pnpm test` | Vitest component tests, one-shot |
| `pnpm lint` | Lint (oxlint, the Vite template's zero-config setup) |
