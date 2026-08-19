# Agent safety: propose → approve → apply

The safety model from the README, as actually implemented. The core claim:
**no agent in this toolkit can write to your CRM without a human decision**,
and the interesting part is that most of the guarantees are structural — they
hold because the code paths don't exist, not because a flag is checked.

## The harness

Every agent runs through one engine, `run_proposals` in
`src/ghl_toolkit/agents/harness.py`:

```
PROPOSE  →  the agent reads data and produces Proposal objects (never a write)
APPROVE  →  an approver callback decides per proposal (CLI confirm, or the
            dashboard's approve button — the HTTP call IS the decision)
APPLY    →  only approved proposals reach apply_fn; every applied change
            appends a structured entry to the audit log
```

Structural properties, each pinned by a test in `tests/test_harness.py`:

- **Dry-run is the default and is structural.** In `dry_run` mode the function
  returns before the approver or apply function is ever invoked — there is no
  code path from a dry run to a write. `--apply` is the only way in.
- **Rejections write nothing.** No HTTP call, no audit entry. The audit log is
  the record of writes; a rejection isn't one.
- **One failure doesn't kill the batch.** An `ApiError` from one apply is
  counted and reported; the rest of the batch continues.
- The harness imports no CLI or rendering code, which is why the webhook
  server drives the identical flow headless.

## What each agent can and cannot do

| Agent | Proposes | Apply writes | Cannot |
| --- | --- | --- | --- |
| `lead_tagger` | net-new tags from your rules file | `POST /contacts/{id}/tags` | invent tags, remove tags, touch any other field |
| `reply_drafter` | a reply draft | **nothing** — records the draft in the audit log | send anything, ever |
| `lead_scorer` | a 0–100 score | one custom field via `PUT /contacts/{id}` | write to an unresolved field, create fields |

The write surface of the entire codebase is three endpoints: contacts search
(read semantics), add-tags, and the contact update the scorer uses. There is
no message-send, email, or SMS capability anywhere — the drafter's apply step
takes no API client at all (`apply_draft(proposal)`), so "it never sends on
its own" is enforced by the function signature, not by policy.

## Constrained outputs

- **Tags:** the model chooses only from your `tagging-rules.yaml` vocabulary.
  A tag it invents is dropped deterministically after validation
  (`lead_tagger.propose_for_contact`) — it can never reach a proposal, and the
  CLI tells you it was dropped. Only net-new tags are proposed.
- **Scores:** `ScoreProposal` bounds the score to 0–100 with pydantic; an
  out-of-range answer fails validation and rides the malformed-output retry
  loop instead of reaching a proposal. The target field id is resolved
  read-only by key — or an explicitly configured id is verified by fetch —
  before any apply, and the apply closure uses only that resolved id.
- **Budget:** every LLM call is gated by a per-run USD hard stop; refusals and
  malformed attempts charge the budget too, so cost is bounded even when the
  model misbehaves. Every attempt is traced to JSONL.

## The audit log

`src/ghl_toolkit/audit.py` — append-only JSONL, one entry per applied change:
timestamp, agent, action, target, before/after, the agent's reasoning, the
approval mode (`interactive` from the CLI, `api` from the dashboard/server),
and the API's response. The dashboard shows an applied proposal's audit entry
in place of its approve/reject buttons; `GET /audit` serves the same data.

## The webhook path

A webhook can only ever create a *pending proposal* (`server/main.py` — the
handler's code path ends at the proposal store). Approval is a separate,
human-initiated HTTP call. So the blast radius of a forged webhook is a
pending proposal someone must review — annoying, not destructive. Defenses in
depth, both optional: a shared-secret header for unsigned workflow webhooks,
and Ed25519 signature verification against GHL's published public key for the
marketplace channel.

Honesty note: the officially documented webhook payload shape is the
Marketplace-app `ContactCreate` event; whether sub-account workflow webhooks
deliver the same shape is undocumented (VERIFY.md V9/V10). If you point real
traffic at the receiver, capture one real delivery and compare it against
`examples/contact_created.json` before trusting the parse — and please report
what you find.

## What approval does not solve

A human approving proposals is a review gate, not a guarantee the proposal is
good. The gate works when proposals are small, legible, and honest about
reasoning — which is why proposals carry the agent's stated reasoning, why
diffs are shown before/after, and why agents propose the minimum change
(net-new tags, one field, one draft) rather than record-wide updates.
