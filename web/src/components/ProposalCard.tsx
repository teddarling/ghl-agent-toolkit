import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { AuditEntry, StoredProposal } from '../api'
import { ApiError, approveProposal, fetchAudit, rejectProposal } from '../api'

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string')
}

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return new Date(iso).toLocaleString()
}

function TagDiff({ before, after }: { before: unknown; after: unknown }) {
  if (!isStringArray(before) || !isStringArray(after)) {
    // Future agents may propose non-tag changes; show the raw diff honestly.
    return (
      <div className="diff-json">
        <pre>{JSON.stringify(before, null, 2)}</pre>
        <pre>{JSON.stringify(after, null, 2)}</pre>
      </div>
    )
  }
  const added = after.filter((tag) => !before.includes(tag))
  return (
    <div className="tag-diff">
      {before.map((tag) => (
        <span key={tag} className="pill pill-existing">
          {tag}
        </span>
      ))}
      {added.map((tag) => (
        <span key={tag} className="pill pill-added">
          +{tag}
        </span>
      ))}
    </div>
  )
}

function AppliedFooter({ item }: { item: StoredProposal }) {
  const { proposal } = item
  const auditQuery = useQuery({
    queryKey: ['audit', proposal.target_id],
    queryFn: () => fetchAudit(proposal.target_id),
    enabled: item.status === 'applied',
  })
  const entry: AuditEntry | undefined = auditQuery.data?.find(
    (candidate) => candidate.action === proposal.action,
  )
  if (!entry) {
    return <footer className="card-footer footer-applied">✓ Applied</footer>
  }
  const written =
    isStringArray(entry.after) && isStringArray(entry.before)
      ? entry.after.filter((tag) => !(entry.before as string[]).includes(tag)).length
      : null
  return (
    <footer className="card-footer footer-applied">
      ✓ Applied · mode {entry.mode} · {new Date(entry.ts).toLocaleString()}
      {written !== null && ` · ${written} tag${written === 1 ? '' : 's'} written`}
    </footer>
  )
}

export function ProposalCard({ item }: { item: StoredProposal }) {
  const { proposal } = item
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['proposals'] })
  const approve = useMutation({ mutationFn: approveProposal, onSettled: invalidate })
  const reject = useMutation({ mutationFn: rejectProposal, onSettled: invalidate })
  const busy = approve.isPending || reject.isPending
  const mutationError = approve.error ?? reject.error

  return (
    <article className={`card card-${item.status}`}>
      <div className="card-head">
        <span className="agent-chip">{proposal.agent}</span>
        <span className="target">
          <strong>{proposal.target_label}</strong>
          <span className="target-id">{proposal.target_id}</span>
        </span>
        <time className="timestamp" dateTime={item.created_at}>
          {relativeTime(item.created_at)}
        </time>
      </div>

      <TagDiff before={proposal.before} after={proposal.after} />

      <blockquote className="reasoning">{proposal.reasoning}</blockquote>

      {item.status === 'pending' && (
        <footer className="card-footer footer-pending">
          {mutationError && (
            <span className="mutation-error">
              {mutationError instanceof ApiError ? mutationError.detail : String(mutationError)}
            </span>
          )}
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => reject.mutate(proposal.id)}
          >
            {reject.isPending ? 'Rejecting…' : 'Reject'}
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy}
            onClick={() => approve.mutate(proposal.id)}
          >
            {approve.isPending ? 'Applying…' : 'Approve'}
          </button>
        </footer>
      )}
      {item.status === 'applied' && <AppliedFooter item={item} />}
      {item.status === 'failed' && (
        <footer className="card-footer footer-failed">Failed · {item.error}</footer>
      )}
      {item.status === 'rejected' && (
        <footer className="card-footer footer-rejected">
          Rejected{item.decided_at && ` · ${new Date(item.decided_at).toLocaleString()}`}
        </footer>
      )}
    </article>
  )
}
