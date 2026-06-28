import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, AlertCircle, PackageSearch, ArrowLeft } from 'lucide-react'
import ProgressTracker from '../components/ProgressTracker'
import type { AnalysisResult, ProgressMessage } from '../types'

const MAX_RETRIES = 3

export default function Analyze() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<ProgressMessage[]>([])
  const [result, setResult]     = useState<AnalysisResult | null>(null)
  const [wsError, setWsError]   = useState('')
  const [retry, setRetry]       = useState(0)
  const wsRef              = useRef<WebSocket | null>(null)
  const doneRef            = useRef(false)
  const intentionalClose   = useRef(false)
  const retryCountRef      = useRef(0)

  useEffect(() => {
    if (!id) return
    setMessages([])
    setResult(null)
    setWsError('')
    doneRef.current          = false
    intentionalClose.current = false

    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl  = `${scheme}://${window.location.host}/ws/progress/${id}`
    const ws     = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => { /* cookie is sent automatically with the upgrade request */ }

    ws.onmessage = (e) => {
      try {
        const msg: ProgressMessage = JSON.parse(e.data)
        if (msg.status === 'keepalive') return
        setMessages((prev) => [...prev, msg])
        if (msg.status === 'complete' && msg.data) {
          doneRef.current = true
          retryCountRef.current = 0
          setResult(msg.data)
        }
        if (msg.status === 'error') {
          doneRef.current = true
          retryCountRef.current = 0
        }
      } catch { /* ignore parse errors */ }
    }
    ws.onerror = () => setWsError('WebSocket connection failed — check that the backend is running.')
    ws.onclose = () => {
      if (doneRef.current || intentionalClose.current) return
      if (retryCountRef.current < MAX_RETRIES) {
        retryCountRef.current += 1
        setTimeout(() => setRetry((n) => n + 1), 3000)
      } else {
        setWsError('Connection lost. The analysis may still be running — check History for results.')
      }
    }
    return () => {
      intentionalClose.current = true
      ws.close()
    }
  }, [id, retry])

  const isDone      = result !== null
  const hasError    = messages.some((m) => m.status === 'error')
  const zeroResources = isDone && result && result.total_resources === 0

  const statCards = result && !zeroResources ? [
    { label: 'Resources Scanned', value: result.total_resources,  color: '#667eea', border: 'border-indigo-500' },
    { label: 'Issues Found',      value: result.issues_found,      color: '#FF9900', border: 'border-orange-500' },
    {
      label: 'Est. Monthly Savings',
      value: `$${result.estimated_monthly_savings.toLocaleString('en-US', { maximumFractionDigits: 0 })}`,
      color: '#28a745', border: 'border-green-500',
    },
  ] : []

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      <div className="card space-y-6">

        {/* Title */}
        <div style={{ borderLeft: '4px solid #667eea', paddingLeft: '12px' }}>
          <h1 className="text-xl font-bold text-white">
            {isDone ? 'Analysis Complete' : hasError ? 'Analysis Failed' : 'Running Analysis...'}
          </h1>
          {id && (
            <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.72em' }} className="mt-1 font-mono">
              {id}
            </p>
          )}
        </div>

        {wsError && (
          <div className="space-y-2">
            <div className="flex gap-2 bg-red-900/50 border border-red-700 text-red-300 text-sm rounded-lg px-3 py-2">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              {wsError}
            </div>
            <button onClick={() => navigate('/history')} className="btn-ghost flex items-center gap-1.5 text-sm">
              <ArrowLeft size={14} />
              Go to History
            </button>
          </div>
        )}

        <ProgressTracker messages={messages} />

        {zeroResources && (
          <div className="flex flex-col items-center gap-3 py-6" style={{ color: 'var(--color-text-tertiary)' }}>
            <PackageSearch size={32} className="opacity-40" />
            <p className="text-sm text-center">
              No resources found in the selected accounts and regions.<br />
              Try selecting additional regions or services.
            </p>
            <button onClick={() => navigate('/')} className="btn-primary text-sm mt-1">
              Back to Dashboard
            </button>
          </div>
        )}

        {/* Summary stat cards */}
        {statCards.length > 0 && (
          <div className="grid grid-cols-3 gap-3 pt-2">
            {statCards.map(({ label, value, color, border }) => (
              <div key={label} className={`summary-card border-t-4 ${border}`}>
                <p className="text-2xl font-bold" style={{ color }}>{value}</p>
                <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
              </div>
            ))}
          </div>
        )}

        {hasError && !wsError && (
          <button onClick={() => navigate('/history')} className="btn-ghost flex items-center gap-1.5 text-sm">
            <ArrowLeft size={14} />
            Go to History
          </button>
        )}

        {isDone && result && !zeroResources && (
          <button
            onClick={() => navigate(`/report/${id}`)}
            className="btn-primary w-full py-3 flex items-center justify-center gap-2"
          >
            View Full Report
            <ArrowRight size={16} />
          </button>
        )}
      </div>
    </div>
  )
}
