import type { AuditEntry, StoredProposal } from "./api";

export const pendingProposal = {
  proposal: {
    id: "prop_test001",
    agent: "lead_tagger",
    action: "contact.add_tags",
    target_type: "contact",
    target_id: "con_test001",
    target_label: "Jane Testerly <jane@x.test>",
    before: ["newsletter"],
    after: ["newsletter", "hot-lead"],
    reasoning: "Contact mentions budget and timeline — matches the hot-lead rule.",
  },
  status: "pending",
  source: "webhook",
  created_at: "2026-08-19T14:30:00.000Z",
  decided_at: null,
  error: null,
  result: null,
} satisfies StoredProposal;

export const appliedProposal = {
  ...pendingProposal,
  proposal: { ...pendingProposal.proposal, id: "prop_test002" },
  status: "applied",
  decided_at: "2026-08-19T14:35:00.000Z",
  result: { tags: ["hot-lead"] },
} satisfies StoredProposal;

export const auditEntry = {
  ts: "2026-08-19T14:35:00.000Z",
  agent: "lead_tagger",
  action: "contact.add_tags",
  target_type: "contact",
  target_id: "con_test001",
  before: ["newsletter"],
  after: ["newsletter", "hot-lead"],
  reasoning: "Contact mentions budget and timeline — matches the hot-lead rule.",
  mode: "api",
  result: { tags: ["hot-lead"] },
} satisfies AuditEntry;
