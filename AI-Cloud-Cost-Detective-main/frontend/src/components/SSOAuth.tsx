import { useEffect, useRef, useState } from 'react'
import { ExternalLink, RefreshCw, CheckCircle, AlertTriangle, LogIn, ChevronDown } from 'lucide-react'
import { sso, saveSSOCreds, loadSSOCreds, clearSSOCreds, type SSOCredential } from '../api'

const SSO_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'eu-west-1', 'eu-west-2', 'eu-central-1', 'eu-north-1',
  'ap-northeast-1', 'ap-northeast-2', 'ap-southeast-1', 'ap-southeast-2',
  'ap-south-1', 'ca-central-1', 'sa-east-1',
]

interface AccountWithRole {
  account_id: string
  account_name: string
  email: string
  roles: string[]
  selectedRole: string
  checked: boolean
}

interface Props {
  onComplete: (creds: SSOCredential[]) => void
  onCancel: () => void
}

type Step = 'init' | 'authorizing' | 'picking' | 'fetching' | 'done'

export default function SSOAuth({ onComplete, onCancel }: Props) {
  // ── Step 1: URL entry ──────────────────────────────────────────────
  const [startUrl, setStartUrl] = useState('')
  const [region, setRegion]     = useState('us-east-1')
  const [starting, setStarting] = useState(false)

  // ── Step 2: Device auth ────────────────────────────────────────────
  const [step, setStep]         = useState<Step>('init')
  const [sessionId, setSessionId] = useState('')
  const [userCode, setUserCode] = useState('')
  const [verifyUrl, setVerifyUrl] = useState('')
  const [verifyUrlComplete, setVerifyUrlComplete] = useState('')
  const [pollInterval, setPollInterval] = useState(5)
  const [expiresIn, setExpiresIn] = useState(0)
  const [timeLeft, setTimeLeft] = useState(0)
  const [pollError, setPollError] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Step 3: Account picker ─────────────────────────────────────────
  const [accounts, setAccounts] = useState<AccountWithRole[]>([])
  const [loadingAccounts, setLoadingAccounts] = useState(false)
  const [fetchingCreds, setFetchingCreds] = useState(false)
  const [pickError, setPickError] = useState('')

  // ── Existing creds ─────────────────────────────────────────────────
  const existing = loadSSOCreds()

  // Cleanup intervals on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      if (countdownRef.current) clearInterval(countdownRef.current)
    }
  }, [])

  const stopPolling = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
    if (countdownRef.current) { clearInterval(countdownRef.current); countdownRef.current = null }
  }

  const startPolling = (sid: string, interval: number, expires: number) => {
    setTimeLeft(expires)
    countdownRef.current = setInterval(() => {
      setTimeLeft((t) => Math.max(t - 1, 0))
    }, 1000)

    pollRef.current = setInterval(async () => {
      try {
        const result = await sso.poll(sid)
        if (result.status === 'authorized') {
          stopPolling()
          setStep('picking')
          setLoadingAccounts(true)
          try {
            const { accounts: raw } = await sso.accounts(sid)
            setAccounts(
              raw.map((a) => ({
                ...a,
                selectedRole: a.roles[0] ?? '',
                checked: true,
              }))
            )
          } catch (e: unknown) {
            setPickError(e instanceof Error ? e.message : 'Failed to load accounts')
          } finally {
            setLoadingAccounts(false)
          }
        } else if (result.status === 'expired' || result.status === 'error') {
          stopPolling()
          setPollError(result.message ?? 'Authorization failed. Please try again.')
          setStep('init')
        }
      } catch {
        // network hiccup — keep polling
      }
    }, interval * 1000)
  }

  const handleStart = async () => {
    if (!startUrl.trim()) return
    setStarting(true)
    setPollError('')
    try {
      const res = await sso.start(startUrl.trim(), region)
      setSessionId(res.session_id)
      setUserCode(res.user_code)
      setVerifyUrl(res.verification_uri)
      setVerifyUrlComplete(res.verification_uri_complete)
      setPollInterval(res.interval)
      setExpiresIn(res.expires_in)
      setStep('authorizing')
      startPolling(res.session_id, res.interval, res.expires_in)
    } catch (e: unknown) {
      setPollError(e instanceof Error ? e.message : 'Failed to start SSO login')
    } finally {
      setStarting(false)
    }
  }

  const handleUseAccounts = async () => {
    const selected = accounts.filter((a) => a.checked && a.selectedRole)
    if (selected.length === 0) { setPickError('Select at least one account.'); return }
    setPickError('')
    setFetchingCreds(true)
    try {
      const { credentials, errors } = await sso.credentials(
        sessionId,
        selected.map((a) => ({ account_id: a.account_id, account_name: a.account_name, role_name: a.selectedRole }))
      )
      if (credentials.length === 0 && errors.length > 0) {
        setPickError(`Could not get credentials: ${errors.join('; ')}`)
        return
      }
      saveSSOCreds(credentials)
      setStep('done')
      onComplete(credentials)
    } catch (e: unknown) {
      setPickError(e instanceof Error ? e.message : 'Failed to fetch credentials')
    } finally {
      setFetchingCreds(false)
    }
  }

  const handleReauth = () => {
    clearSSOCreds()
    setStep('init')
    setSessionId('')
    setUserCode('')
    setPollError('')
    setAccounts([])
    setPickError('')
  }

  const toggleAll = (checked: boolean) =>
    setAccounts((prev) => prev.map((a) => ({ ...a, checked })))

  const selectedCount = accounts.filter((a) => a.checked && a.selectedRole).length
  const minutes = Math.floor(timeLeft / 60)
  const seconds = timeLeft % 60

  // ── Existing session: already connected ───────────────────────────
  if (existing && existing.length > 0 && step === 'init') {
    return (
      <div className="space-y-4">
        <div className="rounded-xl p-4 flex items-start gap-3"
          style={{ background: 'rgba(34,197,94,0.1)', border: '1px solid rgba(34,197,94,0.4)' }}>
          <CheckCircle size={18} style={{ color: '#4ade80', marginTop: '1px', flexShrink: 0 }} />
          <div>
            <p className="text-sm font-medium text-white">SSO Connected</p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
              {existing.length} account{existing.length !== 1 ? 's' : ''} ready:{' '}
              {existing.map((c) => c.account_name || c.account_id).join(', ')}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onComplete(existing)}
            className="btn-primary flex-1 py-2.5 text-sm flex items-center justify-center gap-2">
            <CheckCircle size={15} />
            Use These Accounts
          </button>
          <button
            onClick={handleReauth}
            className="btn-ghost px-4 py-2.5 text-sm">
            Re-authenticate
          </button>
        </div>
      </div>
    )
  }

  // ── Step 1: Enter SSO URL ──────────────────────────────────────────
  if (step === 'init') {
    return (
      <div className="space-y-4">
        {pollError && (
          <div className="rounded-lg p-3 flex items-start gap-2"
            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.4)' }}>
            <AlertTriangle size={14} style={{ color: '#f87171', marginTop: '1px', flexShrink: 0 }} />
            <p className="text-xs" style={{ color: '#fca5a5' }}>{pollError}</p>
          </div>
        )}

        <div>
          <label className="block text-xs mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            SSO Start URL <span style={{ color: '#f87171' }}>*</span>
          </label>
          <input
            className="input w-full text-sm font-mono"
            placeholder="https://mycompany.awsapps.com/start"
            value={startUrl}
            onChange={(e) => setStartUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleStart()}
            autoComplete="off"
          />
          <p className="text-xs mt-1" style={{ color: 'var(--color-text-tertiary)' }}>
            Found in AWS IAM Identity Center → Settings → AWS access portal URL
          </p>
        </div>

        <div>
          <label className="block text-xs mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
            Identity Center Region
          </label>
          <div className="relative">
            <select
              className="input w-full text-sm"
              value={region}
              onChange={(e) => setRegion(e.target.value)}
              style={{ appearance: 'none', paddingRight: '28px', background: 'var(--color-select-bg)', color: 'var(--color-select-text)' }}>
              {SSO_REGIONS.map((r) => (
                <option key={r} value={r} style={{ background: '#0f1432' }}>{r}</option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
              style={{ color: 'var(--color-text-tertiary)' }} />
          </div>
        </div>

        <div className="flex gap-2">
          <button
            onClick={handleStart}
            disabled={!startUrl.trim() || starting}
            className="btn-primary flex-1 py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
            {starting
              ? <><RefreshCw size={15} className="animate-spin" /> Connecting…</>
              : <><LogIn size={15} /> Connect with AWS SSO</>}
          </button>
          <button onClick={onCancel} className="btn-ghost px-4 py-2.5 text-sm">Cancel</button>
        </div>

        <div className="rounded-lg p-3 text-xs leading-relaxed space-y-1"
          style={{ background: 'var(--color-section-bg)', color: 'var(--color-text-secondary)' }}>
          <p className="font-medium" style={{ color: 'var(--color-text-secondary)' }}>Works with any identity provider federated through AWS IAM Identity Center:</p>
          <p>Okta · Azure AD / Entra ID · Google Workspace · Ping Identity · OneLogin · Active Directory</p>
        </div>
      </div>
    )
  }

  // ── Step 2: Waiting for browser authorization ──────────────────────
  if (step === 'authorizing') {
    return (
      <div className="space-y-4">
        <div className="text-center space-y-1">
          <p className="text-sm font-medium text-white">Authorize in your browser</p>
          <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
            Expires in {minutes}:{String(seconds).padStart(2, '0')}
          </p>
        </div>

        {/* User code */}
        <div className="rounded-xl p-4 text-center"
          style={{ background: 'rgba(255,153,0,0.1)', border: '2px solid rgba(255,153,0,0.5)' }}>
          <p className="text-xs mb-2" style={{ color: 'var(--color-text-secondary)' }}>Enter this code when prompted</p>
          <p className="text-3xl font-bold tracking-[0.3em] font-mono" style={{ color: '#fbbf24' }}>
            {userCode}
          </p>
        </div>

        {/* Open browser */}
        <a
          href={verifyUrlComplete}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 w-full py-2.5 rounded-xl text-sm font-medium transition-all"
          style={{
            background: 'rgba(99,102,241,0.2)',
            border: '1px solid rgba(99,102,241,0.5)',
            color: '#a5b4fc',
          }}>
          <ExternalLink size={15} />
          Open Authorization Page
        </a>

        <p className="text-xs text-center" style={{ color: 'var(--color-text-tertiary)' }}>
          Or open manually: <span className="font-mono break-all" style={{ color: 'var(--color-text-secondary)' }}>{verifyUrl}</span>
        </p>

        <div className="flex items-center justify-center gap-2 py-2" style={{ color: 'var(--color-text-secondary)' }}>
          <RefreshCw size={14} className="animate-spin" />
          <span className="text-xs">Checking every {pollInterval}s…</span>
        </div>

        <button onClick={() => { stopPolling(); setStep('init') }}
          className="btn-ghost w-full py-2 text-sm">
          Cancel
        </button>
      </div>
    )
  }

  // ── Step 3: Account + role picker ─────────────────────────────────
  if (step === 'picking') {
    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-white flex items-center gap-2">
            <CheckCircle size={16} style={{ color: '#4ade80' }} />
            Authorized — select accounts to scan
          </p>
          <div className="flex gap-3 text-xs">
            <button onClick={() => toggleAll(true)} style={{ color: '#a5b4fc' }} className="hover:text-white transition-colors">All</button>
            <span style={{ color: 'var(--color-text-tertiary)' }}>|</span>
            <button onClick={() => toggleAll(false)} style={{ color: 'var(--color-text-tertiary)' }} className="hover:text-white transition-colors">None</button>
          </div>
        </div>

        {loadingAccounts ? (
          <div className="flex items-center gap-2 py-4" style={{ color: 'var(--color-text-tertiary)' }}>
            <RefreshCw size={14} className="animate-spin" />
            <span className="text-xs">Loading your accounts…</span>
          </div>
        ) : (
          <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
            {accounts.length === 0 && (
              <p className="text-xs py-3" style={{ color: 'var(--color-text-tertiary)' }}>
                No accounts found. Your SSO role may not have access to any AWS accounts.
              </p>
            )}
            {accounts.map((acct) => (
              <div
                key={acct.account_id}
                className="rounded-lg px-3 py-2.5 transition-all cursor-pointer"
                style={{
                  background: acct.checked ? 'rgba(255,153,0,0.1)' : 'var(--color-section-bg)',
                  border: acct.checked ? '1px solid rgba(255,153,0,0.5)' : '1px solid var(--color-section-border)',
                }}
                onClick={() =>
                  setAccounts((prev) =>
                    prev.map((a) => a.account_id === acct.account_id ? { ...a, checked: !a.checked } : a)
                  )
                }>
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={acct.checked}
                    onChange={() => {}}
                    onClick={(e) => e.stopPropagation()}
                    className="shrink-0"
                  />
                  <span className="font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{acct.account_id}</span>
                  <span className="text-sm font-medium text-white flex-1 truncate">{acct.account_name}</span>
                  {acct.email && (
                    <span className="text-xs truncate" style={{ color: 'var(--color-text-tertiary)' }}>{acct.email}</span>
                  )}
                </div>
                {acct.roles.length > 1 ? (
                  <div className="mt-1.5 ml-6 relative" onClick={(e) => e.stopPropagation()}>
                    <select
                      className="input w-full text-xs py-1"
                      value={acct.selectedRole}
                      onChange={(e) =>
                        setAccounts((prev) =>
                          prev.map((a) => a.account_id === acct.account_id ? { ...a, selectedRole: e.target.value } : a)
                        )
                      }
                      style={{ appearance: 'none', paddingRight: '24px', background: 'var(--color-select-bg)', color: 'var(--color-select-text)' }}>
                      {acct.roles.map((r) => (
                        <option key={r} value={r} style={{ background: '#0f1432' }}>{r}</option>
                      ))}
                    </select>
                    <ChevronDown size={11} className="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none"
                      style={{ color: 'var(--color-text-tertiary)' }} />
                  </div>
                ) : acct.roles.length === 1 ? (
                  <p className="mt-1 ml-6 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                    Role: {acct.roles[0]}
                  </p>
                ) : (
                  <p className="mt-1 ml-6 text-xs" style={{ color: '#f87171' }}>No accessible roles</p>
                )}
              </div>
            ))}
          </div>
        )}

        {pickError && (
          <p className="text-xs flex items-center gap-1.5" style={{ color: '#f87171' }}>
            <AlertTriangle size={13} className="shrink-0" />
            {pickError}
          </p>
        )}

        <div className="flex gap-2 pt-1">
          <button
            onClick={handleUseAccounts}
            disabled={fetchingCreds || selectedCount === 0 || loadingAccounts}
            className="btn-primary flex-1 py-2.5 text-sm flex items-center justify-center gap-2 disabled:opacity-50">
            {fetchingCreds
              ? <><RefreshCw size={15} className="animate-spin" /> Getting credentials…</>
              : <><CheckCircle size={15} /> Use {selectedCount > 0 ? `${selectedCount} ` : ''}Account{selectedCount !== 1 ? 's' : ''}</>
            }
          </button>
          <button onClick={() => { stopPolling(); setStep('init') }} className="btn-ghost px-4 py-2.5 text-sm">
            Back
          </button>
        </div>
      </div>
    )
  }

  return null
}
