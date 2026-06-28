import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { auth } from '../api'
import { useAuth } from '../AuthContext'
import { AlertCircle } from 'lucide-react'
import LinkedInBadge from '../components/LinkedInBadge'

export default function Signup() {
  const { login }  = useAuth()
  const navigate   = useNavigate()
  const [searchParams]          = useSearchParams()
  const [email, setEmail]       = useState(searchParams.get('email') ?? '')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm]   = useState('')
  const [error, setError]       = useState('')
  const [loading, setLoading]   = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    if (password !== confirm) { setError('Passwords do not match'); return }
    if (password.length < 8)  { setError('Password must be at least 8 characters'); return }
    setLoading(true)
    try {
      const { user } = await auth.signup(email, password)
      login(user)
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Signup failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4" style={{ position: 'relative' }}>

      {/* Grid overlay */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0,
        backgroundImage: `linear-gradient(var(--color-section-border) 1px, transparent 1px),
                          linear-gradient(90deg, var(--color-section-border) 1px, transparent 1px)`,
        backgroundSize: '52px 52px',
        opacity: 0.6,
      }} />

      {/* Ambient glow */}
      <div style={{ position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 0, overflow: 'hidden' }}>
        <div style={{
          position: 'absolute', width: '600px', height: '600px', borderRadius: '50%',
          background: 'radial-gradient(circle, rgba(99,102,241,0.1) 0%, transparent 65%)',
          top: '-200px', left: '50%', transform: 'translateX(-50%)',
        }} />
      </div>

      <div className="w-full max-w-sm" style={{ position: 'relative', zIndex: 1, animation: 'fadeUp 0.5s ease both' }}>

        {/* Branding */}
        <div className="text-center mb-7">
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '15px',
              background: 'linear-gradient(135deg, #1a3a6e 0%, #2a5298 100%)',
              border: '1px solid rgba(102,162,234,0.3)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 0 7px rgba(99,102,241,0.07), 0 8px 24px rgba(42,82,152,0.38)',
            }}>
              <span style={{ color: '#fff', fontWeight: 900, fontSize: '1.3rem', letterSpacing: '1px', fontFamily: 'Arial, sans-serif' }}>AI</span>
            </div>
          </div>
          <h1 style={{ color: 'var(--color-auth-heading)', fontWeight: 800, fontSize: '1.25rem', letterSpacing: '-0.01em', marginBottom: '5px' }}>
            Cloud Cost Detective
          </h1>
          <p style={{ color: 'var(--color-auth-subtext)', fontSize: '0.82rem' }}>
            Create your account
          </p>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--color-auth-card-bg)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid var(--color-auth-card-border)',
          borderRadius: '18px',
          padding: '32px 28px',
          boxShadow: 'var(--color-auth-card-shadow)',
        }}>
          {error && (
            <div style={{
              display: 'flex', alignItems: 'flex-start', gap: '8px',
              background: 'rgba(254,226,226,0.9)',
              border: '1px solid rgba(252,165,165,0.7)',
              borderRadius: '10px', padding: '10px 14px',
              color: '#b91c1c', fontSize: '0.85rem', marginBottom: '16px',
            }}>
              <AlertCircle size={15} style={{ flexShrink: 0, marginTop: '2px' }} />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {[
              { label: 'Email',            type: 'email',    ph: 'you@company.com', val: email,    set: setEmail,    ac: 'email' },
              { label: 'Password',         type: 'password', ph: 'Min 8 characters', val: password, set: setPassword, ac: 'new-password' },
              { label: 'Confirm Password', type: 'password', ph: 'Repeat password',  val: confirm,  set: setConfirm,  ac: 'new-password' },
            ].map(({ label, type, ph, val, set, ac }) => (
              <div key={label}>
                <label style={{
                  display: 'block',
                  color: 'var(--color-text-secondary)',
                  fontSize: '0.73rem', fontWeight: 600,
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  marginBottom: '6px',
                }}>{label}</label>
                <input
                  type={type}
                  className="input"
                  placeholder={ph}
                  value={val}
                  onChange={(e) => set(e.target.value)}
                  required
                  autoComplete={ac}
                />
              </div>
            ))}

            <button type="submit" disabled={loading} className="btn-primary w-full py-3 mt-1"
              style={{ background: loading ? undefined : 'linear-gradient(135deg, #1a3a6e 0%, #2a5298 100%)' }}>
              {loading ? 'Creating account…' : 'Create Account'}
            </button>
          </form>

          <div style={{ height: '1px', background: 'var(--color-section-border)', margin: '20px 0' }} />

          <p style={{ textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: '0.85rem' }}>
            Already have an account?{' '}
            <Link to="/login" style={{ color: 'var(--color-auth-link)', fontWeight: 600, textDecoration: 'none' }}>
              Sign in
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
