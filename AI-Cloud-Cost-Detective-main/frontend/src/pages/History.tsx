import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Clock, ExternalLink, AlertTriangle, RefreshCw, ChevronDown, LayoutList, LayoutGrid, Trash2 } from 'lucide-react'
import { analysis } from '../api'
import type { HistoryItem } from '../types'

function StatusBadge({ status }: { status: string }) {
  if (status === 'complete') {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full font-medium"
        style={{ background: 'rgba(40,167,69,0.15)', color: '#16a34a', border: '1px solid rgba(40,167,69,0.4)' }}>
        Complete
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="text-xs px-2 py-0.5 rounded-full font-medium"
        style={{ background: 'rgba(220,53,69,0.15)', color: '#dc2626', border: '1px solid rgba(220,53,69,0.4)' }}>
        Failed
      </span>
    )
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded-full font-medium flex items-center gap-1"
      style={{ background: 'rgba(102,126,234,0.15)', color: '#667eea', border: '1px solid rgba(102,126,234,0.4)' }}>
      <RefreshCw size={10} />
      Running
    </span>
  )
}

function fmt(iso: string) {
  if (!iso) return '—'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

const parseSavings = (s: string | null) => parseFloat((s ?? '0').replace(/[^0-9.]/g, '')) || 0

const selectStyle: React.CSSProperties = {
  appearance: 'none',
  background: 'var(--color-select-bg)',
  border: '1px solid var(--color-input-border)',
  color: 'var(--color-select-text)',
  fontSize: '0.82em',
  borderRadius: '8px',
  paddingLeft: '10px',
  paddingRight: '26px',
  paddingTop: '5px',
  paddingBottom: '5px',
  cursor: 'pointer',
  outline: 'none',
}

export default function History() {
  const navigate = useNavigate()
  const [items, setItems]     = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState('')
  const [deletingId, setDeletingId]   = useState<string | null>(null)
  const [confirmId, setConfirmId]     = useState<string | null>(null)
  const [filterStatus, setFilterStatus] = useState<'all' | 'complete' | 'failed' | 'running'>('all')
  const [sortField, setSortField]       = useState<'date' | 'savings' | 'issues'>('date')
  const [viewMode, setViewMode]         = useState<'list' | 'card'>('list')

  const load = useCallback(() => {
    setLoading(true)
    setError('')
    analysis.history()
      .then((r) => setItems(r.analyses))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!items.some((i) => i.status === 'running')) return
    const t = setInterval(load, 15_000)
    return () => clearInterval(t)
  }, [items, load])

  const handleClick = (item: HistoryItem) => {
    if (item.status === 'complete') navigate(`/report/${item.id}`)
    else if (item.status === 'running') navigate(`/analyze/${item.id}`)
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    if (confirmId !== id) { setConfirmId(id); return }
    setConfirmId(null)
    setDeletingId(id)
    try {
      await analysis.delete(id)
      setItems((prev) => prev.filter((i) => i.id !== id))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Delete failed')
    } finally {
      setDeletingId(null)
    }
  }

  const visible = items
    .filter((i) => filterStatus === 'all' || i.status === filterStatus)
    .sort((a, b) => {
      if (sortField === 'savings') return parseSavings(b.estimated_savings) - parseSavings(a.estimated_savings)
      if (sortField === 'issues')  return b.issues_found - a.issues_found
      // Default: newest first — explicit sort so switching sort fields and back works correctly
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    })

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">Analysis History</h1>
          <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>Past cost analysis runs</p>
        </div>
        <div className="flex gap-2">
          <button onClick={load} disabled={loading}
            className="btn-ghost flex items-center gap-1.5 text-sm disabled:opacity-50">
            <RefreshCw size={14} />
            Refresh
          </button>
          <button onClick={() => navigate('/')} className="btn-primary flex items-center gap-1.5 text-sm">
            New Analysis
          </button>
        </div>
      </div>

      {error && (
        <div className="card flex items-center gap-3 text-red-400">
          <AlertTriangle size={16} />
          {error}
        </div>
      )}

      {/* Filter + sort bar */}
      {items.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative">
            <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value as typeof filterStatus)}
              style={selectStyle}>
              <option value="all">Status: All</option>
              <option value="complete">Complete</option>
              <option value="running">Running</option>
              <option value="failed">Failed</option>
            </select>
            <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: 'var(--color-text-tertiary)' }} />
          </div>
          <div className="relative">
            <select value={sortField} onChange={(e) => setSortField(e.target.value as typeof sortField)}
              style={selectStyle}>
              <option value="date">Sort: Newest</option>
              <option value="savings">Sort: Savings</option>
              <option value="issues">Sort: Issues</option>
            </select>
            <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: 'var(--color-text-tertiary)' }} />
          </div>
          <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82em' }}>
            {visible.length} of {items.length}
          </span>

          {/* View mode toggle */}
          <div className="ml-auto flex rounded-lg overflow-hidden" style={{ border: '1px solid var(--color-input-border)' }}>
            <button onClick={() => setViewMode('list')} title="Table view" style={{
              background: viewMode === 'list' ? 'rgba(102,126,234,0.2)' : 'var(--color-section-bg)',
              color: viewMode === 'list' ? '#667eea' : 'var(--color-text-tertiary)',
              padding: '5px 10px',
              borderRight: '1px solid var(--color-input-border)',
            }}>
              <LayoutList size={15} />
            </button>
            <button onClick={() => setViewMode('card')} title="Card view" style={{
              background: viewMode === 'card' ? 'rgba(102,126,234,0.2)' : 'var(--color-section-bg)',
              color: viewMode === 'card' ? '#667eea' : 'var(--color-text-tertiary)',
              padding: '5px 10px',
            }}>
              <LayoutGrid size={15} />
            </button>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-2">
          {[1, 2, 3].map((n) => (
            <div key={n} className="card space-y-2">
              <div className="h-4 rounded w-48" style={{ background: 'var(--color-section-bg)' }} />
              <div className="h-3 rounded w-64" style={{ background: 'var(--color-section-bg)' }} />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="card text-center py-12" style={{ color: 'var(--color-text-tertiary)' }}>
          <Clock size={32} className="mx-auto mb-3 opacity-40" />
          <p>No analyses yet. Run your first cost analysis.</p>
          <button onClick={() => navigate('/')} className="btn-primary mt-4 inline-flex">
            Run Analysis
          </button>
        </div>
      ) : visible.length === 0 ? (
        <div className="card text-center py-8" style={{ color: 'var(--color-text-tertiary)' }}>
          No analyses match the current filter.
        </div>
      ) : viewMode === 'list' ? (
        /* ── Table / List view ── */
        <div className="card p-0 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--color-card-border)', background: 'rgba(102,126,234,0.06)' }}>
                  {(['Status', 'Date', 'Regions', 'Resources', 'Issues', 'Savings', ''] as const).map((h) => (
                    <th key={h} className="px-4 py-3 font-semibold text-xs uppercase tracking-wider text-left"
                      style={{ color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((item) => (
                  <tr
                    key={item.id}
                    role={item.status !== 'failed' ? 'button' : undefined}
                    tabIndex={item.status !== 'failed' ? 0 : undefined}
                    onClick={() => item.status !== 'failed' && handleClick(item)}
                    onKeyDown={(e) => e.key === 'Enter' && item.status !== 'failed' && handleClick(item)}
                    className={item.status !== 'failed' ? 'cursor-pointer' : 'cursor-default'}
                    style={{ borderBottom: '1px solid var(--color-card-border)', opacity: item.status === 'failed' ? 0.7 : 1 }}
                    onMouseEnter={(e) => { if (item.status !== 'failed') (e.currentTarget as HTMLElement).style.background = 'rgba(102,126,234,0.06)' }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = '' }}
                  >
                    <td className="px-4 py-3 whitespace-nowrap"><StatusBadge status={item.status} /></td>
                    <td className="px-4 py-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)', fontSize: '0.82em' }}>
                      {fmt(item.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {item.regions.map((r) => (
                          <span key={r} className="text-xs px-1.5 py-0.5 rounded"
                            style={{ background: 'rgba(102,126,234,0.12)', color: '#667eea', border: '1px solid rgba(102,126,234,0.25)' }}>
                            {r}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap" style={{ color: 'var(--color-text-secondary)' }}>
                      {item.resources_scanned}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap" style={{ color: '#FF9900', fontWeight: 600 }}>
                      {item.issues_found}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap" style={{ color: '#16a34a', fontWeight: 600 }}>
                      {item.estimated_savings ?? '—'}
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-right">
                      <div className="flex items-center justify-end gap-2">
                        {item.status === 'complete' && (
                          <ExternalLink size={14} style={{ color: 'var(--color-text-tertiary)' }} />
                        )}
                        {item.status === 'running' && (
                          <RefreshCw size={14} style={{ color: '#667eea' }} />
                        )}
                        {item.status === 'failed' && (
                          <button className="btn-ghost text-xs px-2 py-1"
                            onClick={(e) => { e.stopPropagation(); navigate('/') }}>
                            Retry →
                          </button>
                        )}
                        {item.status !== 'running' && (
                          <button
                            title={confirmId === item.id ? 'Click again to confirm' : 'Delete'}
                            disabled={deletingId === item.id}
                            onClick={(e) => handleDelete(e, item.id)}
                            className="flex items-center gap-1 text-xs px-2 py-1 rounded transition-all"
                            style={{
                              color: confirmId === item.id ? '#dc2626' : 'var(--color-text-tertiary)',
                              background: confirmId === item.id ? 'rgba(220,38,38,0.12)' : 'transparent',
                              border: confirmId === item.id ? '1px solid rgba(220,38,38,0.35)' : '1px solid transparent',
                            }}>
                            {deletingId === item.id
                              ? <RefreshCw size={12} className="animate-spin" />
                              : confirmId === item.id
                                ? <><Trash2 size={12} /> Confirm</>
                                : <Trash2 size={12} />}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* ── Card view ── */
        <div className="space-y-3">
          {visible.map((item) => (
            <div
              key={item.id}
              role={item.status !== 'failed' ? 'button' : undefined}
              tabIndex={item.status !== 'failed' ? 0 : undefined}
              className={`card ${item.status !== 'failed' ? 'cursor-pointer' : 'cursor-default opacity-75'}`}
              style={{ borderColor: item.status === 'failed' ? 'rgba(220,53,69,0.2)' : undefined }}
              onClick={() => item.status !== 'failed' && handleClick(item)}
              onKeyDown={(e) => e.key === 'Enter' && item.status !== 'failed' && handleClick(item)}
              onMouseEnter={(e) => {
                if (item.status !== 'failed')
                  (e.currentTarget as HTMLElement).style.borderColor = 'rgba(102,126,234,0.5)'
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = item.status === 'failed'
                  ? 'rgba(220,53,69,0.2)' : 'var(--color-card-border)'
              }}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-2">
                    <StatusBadge status={item.status} />
                    <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.75em' }}>{fmt(item.created_at)}</span>
                    {item.status === 'failed' && item.error_message && (
                      <span className="text-red-400 text-xs truncate max-w-xs">{item.error_message}</span>
                    )}
                  </div>

                  <div className="flex flex-wrap gap-1 mb-2">
                    {item.regions.map((r) => (
                      <span key={r} className="text-xs px-1.5 py-0.5 rounded"
                        style={{ background: 'rgba(102,126,234,0.12)', color: '#667eea', border: '1px solid rgba(102,126,234,0.25)' }}>
                        {r}
                      </span>
                    ))}
                  </div>

                  <div className="flex flex-wrap gap-3 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                    <span>{item.resources_scanned} resources scanned</span>
                    <span style={{ color: '#FF9900' }}>{item.issues_found} issues</span>
                    {item.estimated_savings && (
                      <span style={{ color: '#16a34a', fontWeight: 600 }}>{item.estimated_savings} savings</span>
                    )}
                  </div>

                  {(item.accounts ?? []).length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {item.accounts!.map((a) => (
                        <span key={a} className="text-xs px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(118,75,162,0.15)', color: '#7c3aed', border: '1px solid rgba(118,75,162,0.3)' }}>
                          {a}
                        </span>
                      ))}
                    </div>
                  )}

                  {item.status === 'failed' && (
                    <button className="btn-ghost text-xs mt-2 px-2 py-1"
                      onClick={(e) => { e.stopPropagation(); navigate('/') }}>
                      Retry →
                    </button>
                  )}
                </div>

                <div className="flex flex-col items-end gap-2 shrink-0">
                  {item.status === 'complete' && (
                    <ExternalLink size={16} style={{ color: 'var(--color-text-tertiary)' }} />
                  )}
                  {item.status === 'running' && (
                    <RefreshCw size={16} style={{ color: '#667eea' }} />
                  )}
                  {item.status !== 'running' && (
                    <button
                      title={confirmId === item.id ? 'Click again to confirm' : 'Delete'}
                      disabled={deletingId === item.id}
                      onClick={(e) => handleDelete(e, item.id)}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded transition-all"
                      style={{
                        color: confirmId === item.id ? '#dc2626' : 'var(--color-text-tertiary)',
                        background: confirmId === item.id ? 'rgba(220,38,38,0.12)' : 'transparent',
                        border: confirmId === item.id ? '1px solid rgba(220,38,38,0.35)' : '1px solid transparent',
                      }}>
                      {deletingId === item.id
                        ? <RefreshCw size={12} className="animate-spin" />
                        : confirmId === item.id
                          ? <><Trash2 size={12} /> Confirm</>
                          : <Trash2 size={12} />}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
