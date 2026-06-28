import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { auth } from '../api'
import { useAuth } from '../AuthContext'
import { AlertCircle } from 'lucide-react'
import LinkedInBadge from '../components/LinkedInBadge'

export default function Login() {
  const { login }   = useAuth()
  const navigate    = useNavigate()
  const [email, setEmail]       = useState('')
  const [password, setPassword] = useState('')
  const [error, setError]         = useState('')
  const [userNotFound, setUserNotFound] = useState(false)
  const [loading, setLoading]     = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setUserNotFound(false)
    setLoading(true)
    try {
      const { user } = await auth.login(email, password)
      login(user)
      navigate('/')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Login failed'
      if (msg.toLowerCase().includes('no account found')) {
        setUserNotFound(true)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4" style={{ position: 'relative' }}>

      {/* Subtle grid */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `linear-gradient(var(--color-section-border) 1px, transparent 1px),
                          linear-gradient(90deg, var(--color-section-border) 1px, transparent 1px)`,
        backgroundSize: '52px 52px',
        opacity: 0.6,
      }} />

      {/* Ambient glow blobs */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', width: '600px', height: '600px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(99,102,241,0.12) 0%, transparent 65%)',
          top: '-200px', left: '50%', transform: 'translateX(-50%)',
        }} />
        <div style={{
          position: 'absolute', width: '400px', height: '400px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(124,58,237,0.08) 0%, transparent 65%)',
          bottom: '-100px', right: '20%',
        }} />
      </div>

      <div className="w-full max-w-sm" style={{ position: 'relative', zIndex: 1, animation: 'fadeUp 0.5s ease both' }}>

        {/* Hero branding */}
        <div className="text-center mb-8">
          {/* Logo ring */}
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '20px' }}>
            <div style={{
              width: '76px', height: '76px', borderRadius: '18px',
              background: 'linear-gradient(135deg, #1a3a6e 0%, #2a5298 100%)',
              border: '1px solid rgba(102,162,234,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 0 8px rgba(99,102,241,0.08), 0 8px 28px rgba(42,82,152,0.4)',
              position: 'relative',
            }}>
              <span style={{ color: '#fff', fontWeight: 900, fontSize: '1.5rem', letterSpacing: '1px', fontFamily: 'Arial, sans-serif' }}>AI</span>
            </div>
          </div>

          <h1 style={{ color: 'var(--color-auth-heading)', fontWeight: 800, fontSize: '1.35rem', letterSpacing: '-0.01em', marginBottom: '6px' }}>
            Cloud Cost Detective
          </h1>
          <p style={{ color: 'var(--color-auth-subtext)', fontSize: '0.82rem', letterSpacing: '0.04em' }}>
            Multi-Cloud Cost Intelligence
          </p>

          {/* Cloud provider pills */}
          <div style={{ display: 'flex', justifyContent: 'center', gap: '6px', marginTop: '14px' }}>
            {[
              { label: 'AWS',   bg: '#FF9900' },
              { label: 'Azure', bg: '#0078D4' },
              { label: 'GCP',   bg: '#4285F4' },
            ].map(({ label, bg }) => (
              <span key={label} style={{
                background: bg, borderRadius: '5px',
                padding: '2px 8px', fontSize: '0.6rem', fontWeight: 800,
                color: '#fff', letterSpacing: '0.8px',
              }}>{label}</span>
            ))}
          </div>
        </div>

        {/* Login card */}
        <div style={{
          background: 'var(--color-auth-card-bg)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid var(--color-auth-card-border)',
          borderRadius: '18px',
          padding: '32px 28px',
          boxShadow: 'var(--color-auth-card-shadow)',
        }}>
          <p style={{
            color: 'var(--color-text-tertiary)',
            fontSize: '0.72rem',
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            fontWeight: 600,
            marginBottom: '20px',
            textAlign: 'center',
          }}>Sign in to your account</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            {userNotFound && (
              <div style={{
                display: 'flex', flexDirection: 'column', gap: '6px',
                background: 'rgba(255,237,213,0.95)',
                border: '1px solid rgba(251,146,60,0.6)',
                borderRadius: '10px',
                padding: '12px 14px',
                color: '#92400e',
                fontSize: '0.85rem',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600 }}>
                  <AlertCircle size={15} style={{ flexShrink: 0 }} />
                  No account found for <strong>{email}</strong>
                </div>
                <div>
                  Would you like to{' '}
                  <Link
                    to={`/signup?email=${encodeURIComponent(email)}`}
                    style={{ color: '#c2410c', fontWeight: 700, textDecoration: 'underline' }}
                  >
                    create an account
                  </Link>
                  ?
                </div>
              </div>
            )}

            {error && (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: '8px',
                background: 'rgba(254,226,226,0.9)',
                border: '1px solid rgba(252,165,165,0.7)',
                borderRadius: '10px',
                padding: '10px 14px',
                color: '#b91c1c',
                fontSize: '0.85rem',
              }}>
                <AlertCircle size={15} style={{ flexShrink: 0, marginTop: '2px' }} />
                {error}
              </div>
            )}

            <div>
              <label style={{
                display: 'block',
                color: 'var(--color-text-secondary)',
                fontSize: '0.73rem',
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                marginBottom: '6px',
              }}>Email</label>
              <input
                type="email"
                required
                className="input"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div>
              <label style={{
                display: 'block',
                color: 'var(--color-text-secondary)',
                fontSize: '0.73rem',
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                marginBottom: '6px',
              }}>Password</label>
              <input
                type="password"
                required
                className="input"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full py-3 mt-1"
              style={{ background: loading ? undefined : 'linear-gradient(135deg, #1a3a6e 0%, #2a5298 100%)' }}
            >
              {loading ? 'Signing in…' : 'Sign In'}
            </button>
          </form>

          <div style={{ height: '1px', background: 'var(--color-section-border)', margin: '20px 0' }} />

          <p style={{ textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: '0.85rem' }}>
            No account?{' '}
            <Link to="/signup" style={{ color: 'var(--color-auth-link)', fontWeight: 600, textDecoration: 'none' }}>
              Create one
            </Link>
          </p>
        </div>

        <div className="flex justify-center mt-6">
          <LinkedInBadge />
        </div>
      </div>
    </div>
  )
}
