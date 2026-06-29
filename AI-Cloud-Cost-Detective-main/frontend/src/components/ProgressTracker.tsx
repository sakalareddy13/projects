import { CheckCircle2, AlertCircle, Loader2 } from 'lucide-react'
import type { ProgressMessage } from '../types'

interface Props {
  messages: ProgressMessage[]
}

export default function ProgressTracker({ messages }: Props) {
  if (messages.length === 0) {
    return (
      <div className="flex items-center gap-3 py-4" style={{ color: 'var(--color-text-secondary)' }}>
        <Loader2 size={18} className="animate-spin" style={{ color: '#667eea' }} />
        <span>Connecting...</span>
      </div>
    )
  }

  const visible = messages.filter((m) => m.status !== 'keepalive')

  return (
    <ol className="space-y-2">
      {visible.map((msg, i) => {
        const isLast    = i === visible.length - 1
        const isDone    = msg.status === 'complete'
        const isError   = msg.status === 'error'
        const isRunning = isLast && !isDone && !isError

        const textColor = isError   ? '#ef4444'
                        : isDone    ? '#22c55e'
                        : isRunning ? 'var(--color-text)'
                        : 'var(--color-text-secondary)'

        return (
          <li key={i} className="flex items-start gap-3">
            <span className="mt-0.5 shrink-0">
              {isError ? (
                <AlertCircle size={17} style={{ color: '#ef4444' }} />
              ) : isDone || !isRunning ? (
                <CheckCircle2 size={17} style={{ color: '#22c55e' }} />
              ) : (
                <Loader2 size={17} className="animate-spin" style={{ color: '#667eea' }} />
              )}
            </span>
            <span className="text-sm leading-5" style={{ color: textColor, fontWeight: isRunning ? 500 : 400 }}>
              {msg.message}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
