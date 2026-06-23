import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { AuthProvider } from './AuthContext'
import ErrorBoundary from './components/ErrorBoundary'
import { validateOwnership } from './ownership'
import './index.css'

validateOwnership().then(() => {
  const root = document.getElementById('root')
  if (!root) {
    document.body.textContent = 'Startup error: #root element not found'
    return
  }
  ReactDOM.createRoot(root).render(
    <React.StrictMode>
      <ErrorBoundary>
        <BrowserRouter>
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </ErrorBoundary>
    </React.StrictMode>,
  )
}).catch((err: unknown) => {
  // Only suppress the error display if validateOwnership already wrote the failure UI.
  // For any other startup error, show it so the page is never silently blank.
  if (err instanceof Error && err.message === 'Ownership validation failed') return
  document.body.style.cssText = 'margin:0;background:#0f0f0f;color:#fff;font-family:monospace;display:flex;align-items:center;justify-content:center;min-height:100vh;'
  document.body.textContent = `Startup error: ${err instanceof Error ? err.message : String(err)}`
})
