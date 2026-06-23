import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { auth } from '../api'
import { AlertCircle, CheckCircle2, KeyRound } from 'lucide-react'
import LinkedInBadge from '../components/LinkedInBadge'

export default function ChangePassword() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [newPw,   setNewPw]   = useState('')
  const [confirm, setConfirm] = useState('')
  const [error,   setError]   = useState('')
  const [success, setSuccess] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setSuccess('')
    if (newPw !== confirm) { setError('New passwords do not match'); return }
    if (newPw.length < 8)  { setError('Password must be at least 8 characters'); return }
    if (newPw === current)  { setError('New password must differ from current'); return }
    setLoading(true)
    try {
      const { message } = await auth.changePassword(current, newPw)
      setSuccess(message)
      setCurrent(''); setNewPw(''); setConfirm('')
      setTimeout(() => navigate('/'), 1800)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to change password')
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
        backgroundSize: '52px 52px', opacity: 0.6,
      }} />

      <div className="w-full max-w-sm" style={{ position: 'relative', zIndex: 1, animation: 'fadeUp 0.45s ease both' }}>

        {/* Header */}
        <div className="text-center mb-8">
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
            <div style={{
              width: '56px', height: '56px', borderRadius: '14px',
              background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 0 0 7px rgba(99,102,241,0.08), 0 6px 20px rgba(99,102,241,0.35)',
            }}>
              <KeyRound size={22} color="#fff" />
            </div>
          </div>
          <h1 style={{ color: 'var(--color-auth-heading)', fontWeight: 800, fontSize: '1.5rem', letterSpacing: '-0.01em', marginBottom: '4px' }}>Change Password</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--color-text-secondary)' }}>Update your account password</p>
        </div>

        {/* Card */}
        <div style={{
          background: 'var(--color-auth-card-bg)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid var(--color-auth-card-border)',
          borderRadius: '18px', padding: '28px',
          boxShadow: 'var(--color-auth-card-shadow)',
        }}>
          <form onSubmit={handleSubmit} className="space-y-4">

            {error && (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: '8px',
                background: 'rgba(254,226,226,0.9)',
                border: '1px solid rgba(252,165,165,0.7)',
                borderRadius: '10px', padding: '10px 14px',
                color: '#b91c1c', fontSize: '0.85rem',
              }}>
                <AlertCircle size={15} style={{ flexShrink: 0, marginTop: '2px' }} />
                {error}
              </div>
            )}

            {success && (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: '8px',
                background: 'rgba(220,252,231,0.9)',
                border: '1px solid rgba(134,239,172,0.8)',
                borderRadius: '10px', padding: '10px 14px',
                color: '#15803d', fontSize: '0.85rem',
              }}>
                <CheckCircle2 size={15} style={{ flexShrink: 0, marginTop: '2px' }} />
                {success} — redirecting…
              </div>
            )}

            {[
              { label: 'Current Password', val: current, set: setCurrent, ph: '••••••••' },
              { label: 'New Password',     val: newPw,   set: setNewPw,   ph: 'Min 8 characters' },
              { label: 'Confirm Password', val: confirm,  set: setConfirm, ph: '••••••••' },
            ].map(({ label, val, set, ph }) => (
              <div key={label}>
                <label style={{
                  display: 'block',
                  color: 'var(--color-text-secondary)',
                  fontSize: '0.73rem', fontWeight: 600,
                  letterSpacing: '0.06em', textTransform: 'uppercase',
                  marginBottom: '6px',
                }}>{label}</label>
                <input
                  type="password" required className="input"
                  placeholder={ph} value={val}
                  onChange={(e) => set(e.target.value)}
                />
              </div>
            ))}

            <button type="submit" disabled={loading || !!success} className="btn-primary w-full py-3 mt-1">
              {loading ? 'Updating…' : 'Update Password'}
            </button>
          </form>

          <div style={{ height: '1px', background: 'var(--color-section-border)', margin: '20px 0' }} />

          <p style={{ textAlign: 'center', fontSize: '0.85rem', color: 'var(--color-text-tertiary)' }}>
            <button type="button" onClick={() => navigate(-1)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                color: 'var(--color-auth-link)', fontWeight: 600, fontSize: '0.85rem',
              }}>
              ← Cancel
            </button>
          </p>
        </div>

        <div className="flex justify-center mt-6">
          <LinkedInBadge />
        </div>
      </div>
    </div>
  )
}
