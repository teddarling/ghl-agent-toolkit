import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import type { ProposalStatus } from './api'
import { fetchHealth, listProposals } from './api'
import { ProposalList } from './components/ProposalList'

const TABS: { status: ProposalStatus; label: string }[] = [
  { status: 'pending', label: 'Pending' },
  { status: 'applied', label: 'Applied' },
  { status: 'rejected', label: 'Rejected' },
  { status: 'failed', label: 'Failed' },
]

export default function App() {
  const [filter, setFilter] = useState<ProposalStatus>('pending')
  const health = useQuery({ queryKey: ['health'], queryFn: fetchHealth })
  const pending = useQuery({
    queryKey: ['proposals', 'pending'],
    queryFn: () => listProposals('pending'),
    refetchInterval: 5000,
  })
  const pendingCount = pending.data?.length

  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <div className="wordmark">
            ghl-agent-toolkit
            <span className="wordmark-sub">Approval queue</span>
          </div>
          <div className="header-meta">
            {health.data?.demo_mode && <span className="demo-badge">DEMO MODE</span>}
            {pendingCount !== undefined && pendingCount > 0 && (
              <span className="pending-count" aria-label={`${pendingCount} pending`}>
                {pendingCount} pending
              </span>
            )}
          </div>
        </div>
      </header>
      <main className="app-main">
        <nav className="tabs" aria-label="Filter proposals by status">
          {TABS.map((tab) => (
            <button
              key={tab.status}
              type="button"
              className="tab"
              aria-pressed={filter === tab.status}
              onClick={() => setFilter(tab.status)}
            >
              {tab.label}
              {tab.status === 'pending' && pendingCount !== undefined && pendingCount > 0 && (
                <span className="tab-count">{pendingCount}</span>
              )}
            </button>
          ))}
        </nav>
        <ProposalList filter={filter} />
      </main>
    </>
  )
}
