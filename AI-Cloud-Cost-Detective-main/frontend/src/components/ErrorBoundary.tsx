import { Component, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'

interface Props { children: ReactNode }
interface State { error: Error | null }

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center p-8">
          <div className="card max-w-md w-full space-y-4 text-center">
            <AlertTriangle size={32} className="text-red-400 mx-auto" />
            <h1 className="text-white font-bold text-lg">Something went wrong</h1>
            <p className="text-gray-400 text-sm">{this.state.error.message}</p>
            <button className="btn-primary w-full" onClick={() => window.location.reload()}>
              Reload page
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
