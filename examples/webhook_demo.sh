#!/usr/bin/env bash
# End-to-end webhook demo, no GHL account or API keys required:
# starts the server in demo mode, delivers the sample ContactCreate webhook,
# lists pending proposals, approves the first one, and shows its audit entry.
#
# Run from anywhere:  examples/webhook_demo.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8734}"
BASE="http://127.0.0.1:$PORT"
WORKDIR="$(mktemp -d)"

export GHL_DEMO_MODE=1
export GHL_PROPOSALS_PATH="$WORKDIR/proposals.jsonl"
export GHL_AUDIT_LOG_PATH="$WORKDIR/audit.jsonl"
export GHL_LLM_TRACE_PATH="$WORKDIR/trace.jsonl"

echo "▶ Starting demo server on $BASE (state in $WORKDIR)"
uv run uvicorn server.main:app --port "$PORT" --log-level warning &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 50); do
  if curl -sf "$BASE/healthz" >/dev/null 2>&1; then break; fi
  sleep 0.2
done
curl -sf "$BASE/healthz" >/dev/null || { echo "server did not come up"; exit 1; }

echo "▶ Delivering the sample ContactCreate webhook"
curl -sf -X POST "$BASE/webhooks/ghl" \
  -H "Content-Type: application/json" \
  --data-binary @examples/contact_created.json
echo

echo "▶ Pending proposals"
PENDING=$(curl -sf "$BASE/proposals?status=pending")
export PENDING
uv run python - <<'PY'
import json, os
for record in json.loads(os.environ["PENDING"])["proposals"]:
    p = record["proposal"]
    print(f"  {p['id'][:8]}…  {p['target_label']}: {p['before']} → {p['after']}")
PY

FIRST_ID=$(uv run python -c \
  'import json,os; print(json.loads(os.environ["PENDING"])["proposals"][0]["proposal"]["id"])')

echo "▶ Approving proposal $FIRST_ID"
curl -sf -X POST "$BASE/proposals/$FIRST_ID/approve" >/dev/null

echo "▶ Audit log entry for the applied change"
tail -1 "$GHL_AUDIT_LOG_PATH"

echo "✔ Demo complete: webhook → pending proposal → human approval → applied + audited."
