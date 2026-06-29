import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  AlertTriangle, CheckCircle, Copy, ArrowLeft, TrendingDown,
  Filter, ChevronDown, Download, DollarSign
} from 'lucide-react'
import { analysis } from '../api'
import type { AnalysisResult, Issue } from '../types'

const SEVERITY_ORDER = { high: 0, medium: 1, low: 2 }

function SeverityBadge({ s }: { s: string }) {
  if (s === 'high')   return <span className="badge-high">HIGH</span>
  if (s === 'medium') return <span className="badge-medium">MEDIUM</span>
  return <span className="badge-low">LOW</span>
}

function IssueCard({ issue }: { issue: Issue }) {
  const [copied, setCopied] = useState(false)

  const copy = () => {
    navigator.clipboard.writeText(issue.fix_command).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }).catch(() => {
      // Clipboard API unavailable (insecure context or denied permission) —
      // select the text in the pre element so the user can copy manually.
      const pre = document.querySelector(`[data-fix-id="${issue.resource_id}"]`) as HTMLElement | null
      if (pre) {
        const range = document.createRange()
        range.selectNodeContents(pre)
        window.getSelection()?.removeAllRanges()
        window.getSelection()?.addRange(range)
      }
    })
  }

  const typeColors: Record<string, string> = {
    'over-provisioned': '#f59e0b',
    'unused':           '#ef4444',
    'misconfigured':    '#f97316',
    'non-optimized':    '#6366f1',
  }
  const typeColor = typeColors[issue.issue_type] ?? 'var(--color-text-secondary)'

  return (
    <div className="card space-y-3" style={{ padding: '20px 22px' }}>

      {/* Top row: meta + savings */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          {/* Badges row */}
          <div className="flex flex-wrap items-center gap-2 mb-1.5">
            <span style={{
              background: 'var(--color-section-bg)',
              color: 'var(--color-text-secondary)',
              border: '1px solid var(--color-section-border)',
              borderRadius: '6px', padding: '1px 8px',
              fontSize: '0.7rem', fontWeight: 700,
              letterSpacing: '0.06em', textTransform: 'uppercase',
            }}>{issue.service}</span>
            <SeverityBadge s={issue.severity} />
            <span style={{
              fontSize: '0.72rem', fontWeight: 600,
              color: typeColor,
              background: typeColor + '18',
              border: `1px solid ${typeColor}30`,
              borderRadius: '6px', padding: '1px 7px',
            }}>{issue.issue_type}</span>
          </div>

          {/* Resource name */}
          <p className="text-white font-semibold text-sm truncate" style={{ letterSpacing: '-0.01em' }}>
            {issue.resource_name}
          </p>

          {/* Account + region */}
          {(issue.account_id || issue.account_name || issue.region) && (
            <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.74em', marginTop: '3px' }}>
              {issue.account_id && (
                <span className="font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                  {issue.account_id}
                  {issue.account_name && ` (${issue.account_name})`}{' '}
                </span>
              )}
              {!issue.account_id && issue.account_name && `${issue.account_name} `}
              {issue.region && <span>· {issue.region}</span>}
            </p>
          )}
        </div>

        {/* Savings */}
        <div style={{
          textAlign: 'right', flexShrink: 0,
          background: 'rgba(22,163,74,0.08)',
          border: '1px solid rgba(22,163,74,0.2)',
          borderRadius: '10px', padding: '8px 14px',
        }}>
          <p className="text-green-400 font-bold" style={{ fontSize: '1.2rem', lineHeight: 1 }}>
            ${issue.potential_monthly_savings.toLocaleString('en-US', { maximumFractionDigits: 0 })}
          </p>
          <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.66rem', marginTop: '3px' }}>/month</p>
        </div>
      </div>

      {/* Explanation */}
      <p className="text-gray-300 text-sm leading-relaxed">{issue.explanation}</p>

      {/* Fix command — terminal style */}
      <div style={{ background: 'var(--color-code-bg)', border: '1px solid var(--color-code-border)', borderRadius: '10px', overflow: 'hidden' }}>
        <div className="flex items-center justify-between px-3 py-2"
          style={{ borderBottom: '1px solid var(--color-code-divider)' }}>
          <div className="flex items-center gap-2">
            <div style={{ display: 'flex', gap: '5px' }}>
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#ff5f57' }} />
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#febc2e' }} />
              <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: '#28c840' }} />
            </div>
            <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.72rem' }} className="font-mono">Fix Command</span>
          </div>
          <button onClick={copy}
            className="flex items-center gap-1.5 text-xs transition-all"
            style={{
              color: copied ? '#16a34a' : 'var(--color-text-secondary)',
              background: copied ? 'rgba(22,163,74,0.1)' : 'var(--color-ghost-bg)',
              border: `1px solid ${copied ? 'rgba(22,163,74,0.25)' : 'var(--color-section-border)'}`,
              borderRadius: '6px', padding: '3px 9px',
            }}>
            {copied ? <CheckCircle size={12} /> : <Copy size={12} />}
            {copied ? 'Copied!' : 'Copy'}
          </button>
        </div>
        <pre data-fix-id={issue.resource_id} className="text-xs text-green-400 font-mono px-4 py-3 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed">
          {issue.fix_command}
        </pre>
      </div>
    </div>
  )
}

const selectStyle: React.CSSProperties = {
  appearance: 'none',
  background: 'var(--color-select-bg)',
  border: '1.5px solid var(--color-input-border)',
  color: 'var(--color-select-text)',
  fontSize: '0.82em',
  borderRadius: '9px',
  paddingLeft: '12px', paddingRight: '28px',
  paddingTop: '6px', paddingBottom: '6px',
  cursor: 'pointer', outline: 'none',
}

export default function Report() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [result, setResult]     = useState<AnalysisResult | null>(null)
  const [loading, setLoading]   = useState(true)
  const [error, setError]       = useState('')
  const [filterSeverity, setFilterSeverity] = useState<string>('all')
  const [filterService,  setFilterService]  = useState<string>('all')
  const [filterType,     setFilterType]     = useState<string>('all')
  const [filterAccount,  setFilterAccount]  = useState<string>('all')
  const [sortBy, setSortBy]                 = useState<'severity' | 'savings'>('severity')

  useEffect(() => {
    if (!id) return
    analysis.get(id)
      .then((data) => { if (data.analysis_result) setResult(data.analysis_result); else setError('Analysis result not available yet.') })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  if (loading) return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="card animate-pulse space-y-3">
        <div className="h-6 rounded-xl w-48" style={{ background: 'var(--color-section-bg)' }} />
        <div className="h-4 rounded-xl w-96" style={{ background: 'var(--color-section-bg)' }} />
      </div>
    </div>
  )

  if (error) return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <div className="card flex items-center gap-3 text-red-400">
        <AlertTriangle size={20} /> {error}
      </div>
    </div>
  )

  if (!result) return null

  const services = [...new Set(result.issues.map((i) => i.service))].sort()
  const types    = [...new Set(result.issues.map((i) => i.issue_type))].sort()
  const accounts = [...new Set(result.issues.map((i) => i.account_id).filter(Boolean))].sort() as string[]

  const filtered = result.issues
    .filter((i) => filterSeverity === 'all' || i.severity   === filterSeverity)
    .filter((i) => filterService  === 'all' || i.service    === filterService)
    .filter((i) => filterType     === 'all' || i.issue_type === filterType)
    .filter((i) => filterAccount  === 'all' || i.account_id === filterAccount)
    .sort((a, b) =>
      sortBy === 'severity'
        ? (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3)
        : b.potential_monthly_savings - a.potential_monthly_savings,
    )

  const summaryCards = [
    { label: 'Resources Scanned',    value: result.total_resources,  color: '#6366f1', border: 'border-indigo-500' },
    { label: 'Issues Found',         value: result.issues_found,      color: '#f59e0b', border: 'border-amber-500' },
    {
      label: 'Monthly Savings',
      value: `$${result.estimated_monthly_savings.toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
      color: '#16a34a', border: 'border-green-500',
    },
    {
      label: 'Annual Savings',
      value: `$${result.estimated_annual_savings.toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
      color: '#22c55e', border: 'border-green-400',
    },
  ]

  const exportCSV = () => {
    const header = 'Service,Resource,Region,Account,Severity,Type,Explanation,Fix Command,Monthly Savings\n'
    const rows = filtered.map((i) =>
      [i.service, i.resource_name, i.region, i.account_name ?? '', i.severity, i.issue_type,
       `"${i.explanation.replace(/"/g, '""')}"`,
       `"${i.fix_command.replace(/"/g, '""')}"`,
       i.potential_monthly_savings].join(',')
    ).join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `cost-report-${id}.csv`; a.click(); URL.revokeObjectURL(a.href)
  }

  const exportJSON = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: 'application/json' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = `cost-report-${id}.json`; a.click(); URL.revokeObjectURL(a.href)
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 space-y-6">

      {/* Top bar */}
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="btn-ghost flex items-center gap-1.5 text-sm">
          <ArrowLeft size={15} /> Back
        </button>
        <div className="flex gap-2">
          <button onClick={exportCSV} className="btn-ghost flex items-center gap-1.5 text-xs">
            <Download size={13} /> CSV
          </button>
          <button onClick={exportJSON} className="btn-ghost flex items-center gap-1.5 text-xs">
            <Download size={13} /> JSON
          </button>
        </div>
      </div>

      {/* Summary card */}
      <div className="card space-y-5">
        <div style={{ borderLeft: '3px solid #6366f1', paddingLeft: '14px' }} className="flex items-center gap-3">
          <div style={{
            width: '36px', height: '36px', borderRadius: '10px',
            background: 'linear-gradient(135deg, rgba(99,102,241,0.18) 0%, rgba(124,58,237,0.18) 100%)',
            border: '1px solid rgba(99,102,241,0.25)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <TrendingDown size={18} style={{ color: '#6366f1' }} />
          </div>
          <div>
            <h1 className="text-xl font-bold text-white" style={{ letterSpacing: '-0.01em' }}>Cost Analysis Report</h1>
            <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.74em', marginTop: '2px', fontFamily: 'monospace' }}>{id}</p>
          </div>
        </div>

        <p className="text-gray-300 text-sm leading-relaxed">{result.summary}</p>

        {/* Stat cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {summaryCards.map(({ label, value, color, border }) => (
            <div key={label} className={`summary-card border-t-4 ${border}`}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '4px' }}>
                <p className="text-xl font-bold" style={{ color }}>{value}</p>
                {label.includes('Savings') && <DollarSign size={14} style={{ color, opacity: 0.6 }} />}
              </div>
              <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)', fontWeight: 500 }}>{label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Filters */}
      {result.issues.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <Filter size={14} style={{ color: 'var(--color-text-tertiary)' }} className="shrink-0" />
          {[
            { label: 'Severity', value: filterSeverity, set: setFilterSeverity,
              options: [['all','All'],['high','High'],['medium','Medium'],['low','Low']] as [string,string][] },
            { label: 'Service',  value: filterService,  set: setFilterService,
              options: [['all','All'],...services.map((s) => [s,s] as [string,string])] },
            { label: 'Type',     value: filterType,     set: setFilterType,
              options: [['all','All'],...types.map((t) => [t,t] as [string,string])] },
            ...(accounts.length > 1 ? [{ label: 'Account', value: filterAccount, set: setFilterAccount,
              options: [['all','All'],...accounts.map((a) => [a,a] as [string,string])] }] : []),
          ].map(({ label, value, set, options }) => (
            <div key={label} className="relative">
              <select value={value} onChange={(e) => set(e.target.value)} style={selectStyle}>
                {options.map(([v,l]) => <option key={v} value={v}>{label}: {l}</option>)}
              </select>
              <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--color-text-tertiary)' }} />
            </div>
          ))}
          <div className="relative ml-auto">
            <select value={sortBy} onChange={(e) => setSortBy(e.target.value as 'severity'|'savings')} style={selectStyle}>
              <option value="severity">Sort: Severity</option>
              <option value="savings">Sort: Savings</option>
            </select>
            <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: 'var(--color-text-tertiary)' }} />
          </div>
          <span style={{ color: 'var(--color-text-tertiary)', fontSize: '0.82em', whiteSpace: 'nowrap' }}>
            {filtered.length} issue{filtered.length !== 1 ? 's' : ''}
          </span>
        </div>
      )}

      {/* Issue cards */}
      {filtered.length === 0 ? (
        <div className="card text-center py-10" style={{ color: 'var(--color-text-tertiary)' }}>
          {result.issues.length === 0
            ? '✓ No cost issues detected — your cloud environment looks optimised!'
            : 'No issues match the current filters.'}
        </div>
      ) : (
        <div className="space-y-4">
          {filtered.map((issue) => (
            <IssueCard key={`${issue.resource_id}-${issue.service}-${issue.issue_type}`} issue={issue} />
          ))}
        </div>
      )}
    </div>
  )
}
