import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Settings2, Plus, RefreshCw, Trash2, Key, Users, Building2 } from 'lucide-react'
import { aws, loadSSOCreds, clearSSOCreds, type SSOCredential } from '../api'
import SSOAuth from './SSOAuth'
import type { AWSAccount } from '../types'

export type AwsAuthMode = 'keys' | 'sso' | 'organizations'

export interface EnvConfig {
  cloudProvider: 'aws' | 'azure' | 'gcp'
  useOrganizations: boolean
  selectedAccounts: string[]
  selectedRegions: string[]
  subscriptionId?: string
  projectId?: string
  awsAccessKeyId?: string
  awsSecretAccessKey?: string
  awsAuthMode?: AwsAuthMode
  ssoAccountCount?: number
}

const FALLBACK_AWS_REGIONS = [
  'us-east-1', 'us-east-2', 'us-west-1', 'us-west-2',
  'eu-west-1', 'eu-west-2', 'eu-west-3', 'eu-central-1', 'eu-north-1',
  'ap-northeast-1', 'ap-northeast-2', 'ap-southeast-1', 'ap-southeast-2',
  'ap-south-1', 'sa-east-1', 'ca-central-1', 'me-south-1',
]

const ACCOUNT_ID_RE = /^\d{12}$/
const SAVED_KEY = 'cost_detective_env_config'

const ENV_SENSITIVE_FIELDS: (keyof EnvConfig)[] = ['awsSecretAccessKey']

export function loadSavedConfig(): EnvConfig | null {
  try {
    const raw = localStorage.getItem(SAVED_KEY)
    if (!raw) return null
    const cfg = JSON.parse(raw) as EnvConfig
    if (!cfg.cloudProvider) cfg.cloudProvider = 'aws'
    // Strip any secrets that may have been persisted by older versions
    for (const key of ENV_SENSITIVE_FIELDS) delete cfg[key]
    return cfg
  } catch { return null }
}

interface Props { onSave: (config: EnvConfig) => void }

export default function EnvironmentConfig({ onSave }: Props) {
  const saved = loadSavedConfig()

  const [authMode, setAuthMode] = useState<AwsAuthMode>(
    saved?.awsAuthMode ?? (saved?.useOrganizations ? 'organizations' : 'keys')
  )
  const [ssoCreds, setSsoCreds] = useState<SSOCredential[]>(() => loadSSOCreds() ?? [])

  const [useOrg, setUseOrg]               = useState(saved?.useOrganizations ?? false)
  const [accounts, setAccounts]           = useState<AWSAccount[]>([])
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>(saved?.selectedAccounts ?? [])
  const [loadingAccounts, setLoadingAccounts] = useState(false)
  const [loadError, setLoadError]         = useState('')
  const [showAddForm, setShowAddForm]     = useState(false)
  const [newId, setNewId]                 = useState('')
  const [newName, setNewName]             = useState('')
  const [addError, setAddError]           = useState('')
  const [addingAccount, setAddingAccount] = useState(false)
  const [allRegions, setAllRegions]       = useState<string[]>(FALLBACK_AWS_REGIONS)
  const [regions, setRegions]             = useState<string[]>(
    saved?.selectedRegions?.length ? saved.selectedRegions : ['us-east-1']
  )
  const [awsAccessKeyId, setAwsAccessKeyId]   = useState(saved?.awsAccessKeyId ?? '')
  const [awsSecretAccessKey, setAwsSecretAccessKey] = useState(saved?.awsSecretAccessKey ?? '')
  const [saveError, setSaveError]           = useState('')

  const toggleRegion  = (r: string) =>
    setRegions((prev) => prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r])

  const toggleAccount = (id: string) =>
    setSelectedAccountIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id])

  const loadAccounts = useCallback(async () => {
    setLoadingAccounts(true)
    setLoadError('')
    try {
      const { accounts: data } = await aws.accounts()
      setAccounts(data)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Failed to load accounts'
      setLoadError(msg.includes('AWS_SSO_TOKEN_EXPIRED') ? 'SSO_EXPIRED' : msg)
    } finally {
      setLoadingAccounts(false)
    }
  }, [])

  useEffect(() => {
    aws.regions()
      .then((r) => setAllRegions(r.regions))
      .catch(() => setLoadError('Could not load regions from server — using defaults.'))
  }, [])
  useEffect(() => { if (useOrg) loadAccounts() }, [useOrg, loadAccounts])

  const handleAddAccount = async () => {
    if (!newId.trim() || addingAccount) return
    if (!ACCOUNT_ID_RE.test(newId.trim())) { setAddError('Account ID must be exactly 12 digits.'); return }
    setAddError('')
    setAddingAccount(true)
    try {
      const { account } = await aws.addAccount({ account_id: newId.trim(), name: newName.trim() || newId.trim() })
      setAccounts((prev) => [...prev, account])
      setSelectedAccountIds((prev) => [...new Set([...prev, account.account_id])])
      setNewId(''); setNewName(''); setShowAddForm(false)
    } catch (e: unknown) {
      setAddError(e instanceof Error ? e.message : 'Failed to add account')
    } finally {
      setAddingAccount(false)
    }
  }

  const handleRemoveAccount = async (account_id: string) => {
    try {
      await aws.removeAccount(account_id)
      setAccounts((prev) => prev.filter((a) => a.account_id !== account_id))
      setSelectedAccountIds((prev) => prev.filter((id) => id !== account_id))
    } catch (e: unknown) {
      setLoadError(e instanceof Error ? e.message : 'Failed to remove account')
    }
  }

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    setSaveError('')

    if (authMode === 'keys' && (!awsAccessKeyId.trim() || !awsSecretAccessKey.trim())) {
      setSaveError('Enter your AWS Access Key ID and Secret Access Key before saving.')
      return
    }
    if (authMode === 'sso' && ssoCreds.length === 0) {
      setSaveError('Complete the AWS SSO login before saving.')
      return
    }

    const config: EnvConfig = {
      cloudProvider: 'aws',
      useOrganizations: authMode === 'organizations',
      selectedAccounts: authMode === 'organizations' ? selectedAccountIds : [],
      selectedRegions: regions,
      awsAccessKeyId: authMode === 'keys' ? (awsAccessKeyId.trim() || undefined) : undefined,
      awsSecretAccessKey: authMode === 'keys' ? (awsSecretAccessKey.trim() || undefined) : undefined,
      awsAuthMode: authMode,
      ssoAccountCount: authMode === 'sso' ? ssoCreds.length : undefined,
    }
    try {
      // Strip secrets before persisting — credentials must never survive a browser close
      const safe = { ...config }
      for (const key of ENV_SENSITIVE_FIELDS) delete safe[key]
      localStorage.setItem(SAVED_KEY, JSON.stringify(safe))
    } catch {
      setSaveError('Could not save settings — browser storage may be full or disabled.')
      return
    }
    onSave(config)
  }

  const handleSSOComplete = (creds: SSOCredential[]) => {
    setSsoCreds(creds)
  }

  const handleSSOCancel = () => {
    setAuthMode('keys')
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-2xl" style={{ animation: 'zoomIn 0.5s cubic-bezier(0.175,0.885,0.32,1.275) both' }}>
        <div className="card">
          <div className="flex items-center gap-3 mb-6" style={{ borderLeft: '4px solid #FF9900', paddingLeft: '12px' }}>
            <Settings2 size={22} style={{ color: '#FF9900' }} />
            <div>
              <h1 className="text-xl font-bold text-white">AWS Settings</h1>
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>Configure AWS Organizations and default regions</p>
            </div>
          </div>

          <form onSubmit={handleSave} className="space-y-6">
            {/* Auth mode tabs */}
            <div className="grid grid-cols-3 gap-1.5 rounded-xl p-1"
              style={{ background: 'var(--color-section-bg)' }}>
              {([
                { id: 'keys',          label: 'Access Keys', icon: Key,       desc: 'IAM key pair' },
                { id: 'sso',           label: 'AWS SSO',     icon: Users,     desc: 'Browser login' },
                { id: 'organizations', label: 'Org / Server',icon: Building2, desc: 'Server profiles' },
              ] as const).map(({ id, label, icon: Icon, desc }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => { setAuthMode(id); setSaveError('') }}
                  className="flex flex-col items-center gap-1 py-2.5 rounded-lg text-xs font-medium transition-all"
                  style={{
                    background: authMode === id ? 'rgba(255,153,0,0.2)' : 'transparent',
                    border: authMode === id ? '1px solid rgba(255,153,0,0.6)' : '1px solid transparent',
                    color: authMode === id ? 'var(--color-text)' : 'var(--color-text-secondary)',
                  }}>
                  <Icon size={15} style={{ color: authMode === id ? '#FF9900' : 'var(--color-text-tertiary)' }} />
                  <span>{label}</span>
                  <span className="text-xs font-normal" style={{ color: 'var(--color-text-tertiary)', fontSize: '10px' }}>{desc}</span>
                </button>
              ))}
            </div>

            {/* SSO tab */}
            {authMode === 'sso' && (
              <SSOAuth
                onComplete={handleSSOComplete}
                onCancel={handleSSOCancel}
              />
            )}

            {/* Accounts (Organizations mode) */}
            {authMode === 'organizations' && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-medium text-gray-300">
                    AWS Accounts to scan
                    <span className="ml-2 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>({selectedAccountIds.length} selected)</span>
                  </label>
                  <div className="flex items-center gap-3">
                    <div className="flex gap-2 text-xs">
                      <button type="button"
                        style={{ color: accounts.length > 0 ? '#a5b4fc' : 'var(--color-text-tertiary)' }}
                        className="transition-colors hover:text-white"
                        disabled={accounts.length === 0}
                        onClick={() => setSelectedAccountIds(accounts.map((a) => a.account_id))}>
                        All
                      </button>
                      <span style={{ color: 'var(--color-text-tertiary)' }}>|</span>
                      <button type="button"
                        style={{ color: accounts.length > 0 ? 'var(--color-text-secondary)' : 'var(--color-text-tertiary)' }}
                        className="transition-colors hover:text-white"
                        disabled={accounts.length === 0}
                        onClick={() => setSelectedAccountIds([])}>
                        None
                      </button>
                    </div>
                    <button type="button" onClick={loadAccounts} disabled={loadingAccounts}
                      className="flex items-center gap-1 text-xs disabled:opacity-50 transition-colors"
                      style={{ color: 'var(--color-text-secondary)' }}>
                      <RefreshCw size={12} className={loadingAccounts ? 'animate-spin' : ''} />
                      Refresh
                    </button>
                    <button type="button" onClick={() => { setShowAddForm((v) => !v); setAddError('') }}
                      className="flex items-center gap-1 text-xs transition-colors"
                      style={{ color: '#a5b4fc' }}>
                      <Plus size={12} />
                      Add
                    </button>
                  </div>
                </div>

                {loadError && (
                  loadError === 'SSO_EXPIRED' ? (
                    <div className="rounded-lg p-3 mb-3"
                      style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.4)' }}>
                      <p className="text-red-300 text-xs font-semibold mb-1 flex items-center gap-1">
                        <AlertTriangle size={12} className="shrink-0" />
                        AWS Organizations session expired
                      </p>
                      <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                        Please register your account by running:
                      </p>
                      <code className="block mt-1.5 px-2 py-1 rounded text-xs font-mono"
                        style={{ background: 'rgba(0,0,0,0.4)', color: '#86efac' }}>
                        aws sso login
                      </code>
                      <p className="text-xs mt-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                        Then click Refresh to reload your accounts.
                      </p>
                    </div>
                  ) : (
                    <p className="text-red-400 text-xs mb-2 flex items-center gap-1">
                      <AlertTriangle size={12} className="shrink-0" />
                      {loadError} — add accounts manually below.
                    </p>
                  )
                )}

                {showAddForm && (
                  <div className="rounded-lg p-3 mb-3 space-y-2"
                    style={{ background: 'var(--color-section-bg)', border: '1px solid rgba(255,153,0,0.3)' }}>
                    <div className="flex gap-2">
                      <input className="input flex-1 text-sm font-mono" placeholder="Account ID (e.g. 123456789012)"
                        value={newId} onChange={(e) => setNewId(e.target.value)} maxLength={12} />
                      <input className="input flex-1 text-sm" placeholder="Display name (optional)"
                        value={newName} onChange={(e) => setNewName(e.target.value)} />
                    </div>
                    {addError && <p className="text-red-400 text-xs">{addError}</p>}
                    <div className="flex gap-2 justify-end">
                      <button type="button" onClick={() => { setShowAddForm(false); setAddError(''); setNewId(''); setNewName('') }}
                        className="btn-ghost text-xs px-3 py-1">Cancel</button>
                      <button type="button" onClick={handleAddAccount}
                        disabled={!newId.trim() || addingAccount}
                        className="btn-primary text-xs px-3 py-1 flex items-center gap-1">
                        {addingAccount && <RefreshCw size={10} className="animate-spin" />}
                        {addingAccount ? 'Adding…' : 'Add'}
                      </button>
                    </div>
                  </div>
                )}

                <div className="space-y-1">
                  {accounts.length === 0 && !loadingAccounts && (
                    <p className="text-xs py-2" style={{ color: 'var(--color-text-secondary)' }}>
                      No accounts loaded. Click <span style={{ color: '#a5b4fc' }}>Refresh</span> to fetch from AWS SSO profiles, or{' '}
                      <span style={{ color: '#a5b4fc' }}>Add</span> to add manually.
                    </p>
                  )}
                  {loadingAccounts && (
                    <p className="text-xs py-2 flex items-center gap-1" style={{ color: 'var(--color-text-secondary)' }}>
                      <RefreshCw size={12} className="animate-spin" /> Loading accounts…
                    </p>
                  )}
                  {accounts.map((acct) => {
                    const sel = selectedAccountIds.includes(acct.account_id)
                    return (
                      <div key={acct.account_id}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs cursor-pointer transition-all"
                        style={{
                          background: sel ? 'rgba(255,153,0,0.12)' : 'var(--color-section-bg)',
                          border: sel ? '1px solid rgba(255,153,0,0.5)' : '1px solid var(--color-section-border)',
                          color: sel ? 'var(--color-text)' : 'var(--color-text-secondary)',
                        }}
                        onClick={() => toggleAccount(acct.account_id)}>
                        <input type="checkbox" className="shrink-0"
                          checked={sel} onChange={() => toggleAccount(acct.account_id)}
                          onClick={(e) => e.stopPropagation()} />
                        <span className="font-mono">{acct.account_id}</span>
                        <span className="flex-1 truncate" style={{ color: 'var(--color-text-secondary)' }}>{acct.name}</span>
                        {acct.email && <span className="truncate" style={{ color: 'var(--color-text-tertiary)' }}>{acct.email}</span>}
                        <button type="button" onClick={(e) => { e.stopPropagation(); handleRemoveAccount(acct.account_id) }}
                          className="ml-auto shrink-0 transition-colors"
                          style={{ color: 'var(--color-text-tertiary)' }}
                          onMouseEnter={(e) => (e.currentTarget as HTMLElement).style.color = '#f87171'}
                          onMouseLeave={(e) => (e.currentTarget as HTMLElement).style.color = 'var(--color-text-tertiary)'}>
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )
                  })}
                </div>
                <p className="text-xs mt-2" style={{ color: 'var(--color-text-tertiary)' }}>
                  Accounts are auto-detected from <code style={{ color: '#a5b4fc' }}>~/.aws/config</code> SSO profiles.
                </p>
              </div>
            )}

            {/* Regions */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <label className="text-sm font-medium text-gray-300">
                  Default AWS regions
                  <span className="ml-2 text-xs" style={{ color: 'var(--color-text-tertiary)' }}>({regions.length} selected)</span>
                </label>
                <div className="flex gap-2 text-xs">
                  <button type="button" style={{ color: '#a5b4fc' }} className="hover:text-white transition-colors"
                    onClick={() => setRegions(allRegions)}>All</button>
                  <span style={{ color: 'var(--color-text-tertiary)' }}>|</span>
                  <button type="button" style={{ color: 'var(--color-text-secondary)' }} className="hover:text-white transition-colors"
                    onClick={() => setRegions([])}>None</button>
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {allRegions.map((r) => {
                  const sel = regions.includes(r)
                  return (
                    <label key={r}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs cursor-pointer transition-all"
                      style={{
                        background: sel ? 'rgba(255,153,0,0.12)' : 'var(--color-section-bg)',
                        border: sel ? '1px solid rgba(255,153,0,0.5)' : '1px solid var(--color-section-border)',
                        color: sel ? 'var(--color-text)' : 'var(--color-text-secondary)',
                      }}>
                      <input type="checkbox" className="shrink-0" checked={sel} onChange={() => toggleRegion(r)} />
                      {r}
                    </label>
                  )
                })}
              </div>
            </div>

            {/* Access Keys credentials */}
            {authMode === 'keys' && (
              <div>
                <p className="text-sm font-medium text-gray-300 mb-3">AWS Credentials</p>
                <div className="space-y-3 rounded-lg p-4"
                  style={{ background: 'var(--color-section-bg)', border: '1px solid rgba(165,180,252,0.25)' }}>
                  <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                    Keys are kept in browser localStorage and sent to the backend only when a scan runs. Never stored in the database.
                  </p>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                      Access Key ID <span style={{ color: '#f87171' }}>*</span>
                    </label>
                    <input
                      className="input w-full text-sm font-mono"
                      placeholder="AKIAIOSFODNN7EXAMPLE"
                      value={awsAccessKeyId}
                      onChange={(e) => setAwsAccessKeyId(e.target.value)}
                      autoComplete="off"
                    />
                  </div>
                  <div>
                    <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                      Secret Access Key <span style={{ color: '#f87171' }}>*</span>
                    </label>
                    <input
                      type="password"
                      className="input w-full text-sm font-mono"
                      placeholder="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
                      value={awsSecretAccessKey}
                      onChange={(e) => setAwsSecretAccessKey(e.target.value)}
                      autoComplete="new-password"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Organizations info note */}
            {authMode === 'organizations' && (
              <div className="rounded-lg p-3"
                style={{ background: 'rgba(165,180,252,0.07)', border: '1px solid rgba(165,180,252,0.2)' }}>
                <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                  Organizations mode uses server-side SSO profiles from{' '}
                  <code style={{ color: '#a5b4fc' }}>~/.aws/config</code>. Run{' '}
                  <code style={{ color: '#86efac' }}>aws sso login</code> on the host before scanning.
                </p>
              </div>
            )}

            <div className="flex gap-3 rounded-lg p-3"
              style={{ background: 'rgba(234,179,8,0.1)', border: '1px solid rgba(234,179,8,0.3)' }}>
              <AlertTriangle size={16} style={{ color: '#fbbf24', flexShrink: 0, marginTop: '2px' }} />
              <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-secondary)' }}>
                These settings apply to AWS only. To scan Azure or GCP, select the provider on the main Dashboard.
              </p>
            </div>

            {regions.length === 0 && authMode !== 'sso' && (
              <p className="text-red-400 text-sm">Select at least one region.</p>
            )}

            {saveError && (
              <p className="text-red-400 text-sm flex items-center gap-1.5">
                <AlertTriangle size={14} className="shrink-0" />
                {saveError}
              </p>
            )}

            {authMode !== 'sso' && (
              <button type="submit"
                disabled={
                  regions.length === 0 ||
                  addingAccount ||
                  (authMode === 'keys' && (!awsAccessKeyId.trim() || !awsSecretAccessKey.trim()))
                }
                className="btn-primary w-full py-3 text-base disabled:opacity-50">
                Save & Continue
              </button>
            )}

            {authMode === 'sso' && ssoCreds.length > 0 && (
              <button type="submit" className="btn-primary w-full py-3 text-base">
                Save & Continue ({ssoCreds.length} account{ssoCreds.length !== 1 ? 's' : ''} ready)
              </button>
            )}
          </form>
        </div>
      </div>
    </div>
  )
}
