// Hand-written types mirroring the FastAPI proposals contract (server/main.py).
// `before`/`after`/`result` are `unknown` on purpose: lead_tagger sends tag
// arrays today, but future agents may send other JSON shapes — narrow at render.

export type ProposalStatus = 'pending' | 'applied' | 'rejected' | 'failed'

export interface Proposal {
  id: string
  agent: string
  action: string
  target_type: string
  target_id: string
  target_label: string
  before: unknown
  after: unknown
  reasoning: string
}

export interface StoredProposal {
  proposal: Proposal
  status: ProposalStatus
  source: string
  created_at: string
  decided_at: string | null
  error: string | null
  result: unknown
}

export interface AuditEntry {
  ts: string
  agent: string
  action: string
  target_type: string
  target_id: string
  before: unknown
  after: unknown
  reasoning: string
  mode: string
  result: unknown
}

export interface Health {
  status: string
  demo_mode: boolean
}

export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(`API error ${status}: ${detail}`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    let detail = response.statusText
    try {
      const body = (await response.json()) as { detail?: unknown }
      if (body.detail !== undefined) {
        detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
      }
    } catch {
      // non-JSON error body — keep the status text
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as T
}

export async function listProposals(status?: ProposalStatus): Promise<StoredProposal[]> {
  const query = status ? `?status=${status}` : ''
  const body = await request<{ proposals: StoredProposal[] }>(`/proposals${query}`)
  return body.proposals
}

export function approveProposal(id: string): Promise<StoredProposal> {
  return request<StoredProposal>(`/proposals/${id}/approve`, { method: 'POST' })
}

export function rejectProposal(id: string): Promise<StoredProposal> {
  return request<StoredProposal>(`/proposals/${id}/reject`, { method: 'POST' })
}

export async function fetchAudit(targetId: string): Promise<AuditEntry[]> {
  const body = await request<{ entries: AuditEntry[] }>(
    `/audit?target_id=${encodeURIComponent(targetId)}`,
  )
  return body.entries
}

export function fetchHealth(): Promise<Health> {
  return request<Health>('/healthz')
}
