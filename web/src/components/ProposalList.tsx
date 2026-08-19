import { useQuery } from '@tanstack/react-query'
import type { ProposalStatus } from '../api'
import { listProposals } from '../api'
import { ProposalCard } from './ProposalCard'

const EMPTY_COPY: Record<ProposalStatus, string> = {
  pending: 'No pending proposals. New webhook events will appear here automatically.',
  applied: 'Nothing applied yet — approved proposals land here with their audit entry.',
  rejected: 'No rejected proposals.',
  failed: 'No failed applies — that is how it should be.',
}

export function ProposalList({ filter }: { filter: ProposalStatus }) {
  const query = useQuery({
    queryKey: ['proposals', filter],
    queryFn: () => listProposals(filter),
    refetchInterval: 5000,
  })

  if (query.isPending) {
    return (
      <div className="state-panel" role="status">
        <span className="spinner" aria-hidden="true" />
        Loading proposals…
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="state-panel state-error">
        <p>
          <strong>Can't reach the server.</strong>
        </p>
        <p className="state-hint">
          Start it with <code>GHL_DEMO_MODE=1 uv run uvicorn server.main:app</code>
        </p>
        <button type="button" className="btn btn-primary" onClick={() => query.refetch()}>
          Retry
        </button>
      </div>
    )
  }

  if (query.data.length === 0) {
    return <div className="state-panel">{EMPTY_COPY[filter]}</div>
  }

  return (
    <div className="queue">
      {query.data.map((item) => (
        <ProposalCard key={item.proposal.id} item={item} />
      ))}
    </div>
  )
}
