import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Play, RefreshCw, Cloud, Key, Users, Building2, AlertTriangle, Plus, Trash2 } from 'lucide-react'
import { analysis, cloud, aws as awsApi, loadSSOCreds, clearSSOCreds, type SSOCredential } from '../api'
import ServiceSelector from '../components/ServiceSelector'
import SSOAuth from '../components/SSOAuth'
import type { AWSAccount, CloudProvider } from '../types'

const PROVIDER_META: Record<CloudProvider, { label: string; color: string; bg: string; border: string }> = {
  aws:   { label: 'AWS',   color: '#FF9900', bg: 'rgba(255,153,0,0.18)',   border: 'rgba(255,153,0,0.75)' },
  azure: { label: 'Azure', color: '#0078D4', bg: 'rgba(0,120,212,0.18)',   border: 'rgba(0,120,212,0.75)' },
  gcp:   { label: 'GCP',   color: '#34A853', bg: 'rgba(52,168,83,0.18)',   border: 'rgba(52,168,83,0.75)' },
}

type AwsAuthMode = 'keys' | 'sso' | 'organizations'

const PREFS_KEY = 'cost_detective_dash_prefs'

type Prefs = {
  cloudProvider: CloudProvider
  // AWS
  awsAuthMode: AwsAuthMode
  awsAccessKeyId: string
  awsSecretAccessKey: string
  selectedOrgAccountIds: string[]
  // Azure
  subscriptionId: string
  azureTenantId: string
  azureClientId: string
  azureClientSecret: string
  // GCP
  projectId: string
  gcpApiKey: string
  // AI
  aiProvider: string
  aiApiKey: string
}

function loadPrefs(): Prefs {
  const defaults: Prefs = {
    cloudProvider: 'aws',
    awsAuthMode: 'keys',
    awsAccessKeyId: '',
    awsSecretAccessKey: '',
    selectedOrgAccountIds: [],
    subscriptionId: '',
    azureTenantId: '',
    azureClientId: '',
    azureClientSecret: '',
    projectId: '',
    gcpApiKey: '',
    aiProvider: '',
    aiApiKey: '',
  }
  try {
    const raw = localStorage.getItem(PREFS_KEY)
    if (raw) return { ...defaults, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return defaults
}

// Sensitive credential fields — never written to localStorage
const SENSITIVE_FIELDS = [
  'awsSecretAccessKey', 'azureClientSecret', 'gcpApiKey', 'aiApiKey',
] as const

function savePrefs(prefs: Prefs) {
  // Strip secrets before persisting — credentials must not survive a browser close
  const safe = { ...prefs }
  for (const key of SENSITIVE_FIELDS) delete (safe as Partial<Prefs>)[key]
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(safe)) } catch { /* ignore */ }
}

const AI_PROVIDERS = [
  { value: '',           label: 'Auto-detect (server key)',  placeholder: '' },
  { value: 'anthropic',  label: 'Claude (Anthropic)',        placeholder: 'sk-ant-api03-...' },
  { value: 'openai',     label: 'GPT-4o (OpenAI)',           placeholder: 'sk-proj-...' },
  { value: 'google',     label: 'Gemini (Google)',           placeholder: 'AIzaSy...' },
  { value: 'groq',       label: 'Groq (Llama 3)',            placeholder: 'gsk_...' },
  { value: 'deepseek',   label: 'DeepSeek',                  placeholder: 'sk-...' },
  { value: 'xai',        label: 'Grok (xAI)',                placeholder: 'xai-...' },
  { value: 'mistral',    label: 'Mistral',                   placeholder: 'api key...' },
  { value: 'bedrock',    label: 'AWS Bedrock (no key)',       placeholder: '' },
  { value: 'ollama',     label: 'Ollama (local)',             placeholder: '' },
]

const ACCOUNT_ID_RE = /^\d{12}$/

export default function Dashboard() {
  const navigate = useNavigate()

  const [prefs, setPrefs] = useState(loadPrefs)
  const {
    cloudProvider,
    awsAuthMode, awsAccessKeyId, awsSecretAccessKey, selectedOrgAccountIds,
    subscriptionId, azureTenantId, azureClientId, azureClientSecret,
    projectId, gcpApiKey,
    aiProvider, aiApiKey,
  } = prefs

  const updatePrefs = (patch: Partial<Prefs>) => {
    const next = { ...prefs, ...patch }
    setPrefs(next)
    savePrefs(next)
  }

  // SSO credentials (sessionStorage — gone when tab closes)
  const [ssoCreds, setSsoCreds] = useState<SSOCredential[]>(() => loadSSOCreds() ?? [])

  // Org accounts
  const [orgAccounts, setOrgAccounts]         = useState<AWSAccount[]>([])
  const [loadingOrg, setLoadingOrg]           = useState(false)
  const [orgError, setOrgError]               = useState('')
  const [showAddOrg, setShowAddOrg]           = useState(false)
  const [newOrgId, setNewOrgId]               = useState('')
  const [newOrgName, setNewOrgName]           = useState('')
  const [addingOrg, setAddingOrg]             = useState(false)
  const [addOrgError, setAddOrgError]         = useState('')

  // Regions
  const [allRegions, setAllRegions]           = useState<string[]>([])
  const [selectedRegions, setSelectedRegions] = useState<string[]>([])
  const [loadingRegions, setLoadingRegions]   = useState(false)

  // Services
  const [services, setServices]               = useState<{ id: string; name: string; description: string }[]>([])
  const [selectedServices, setSelectedServices] = useState<string[]>([])
  const [loadingServices, setLoadingServices] = useState(false)
  const [serviceWarning, setServiceWarning]   = useState('')

  const [launching, setLaunching]   = useState(false)
  const [validating, setValidating] = useState(false)
  const [error, setError]           = useState('')

  // Load regions + services when provider changes
  useEffect(() => {
    setLoadingRegions(true)
    setLoadingServices(true)
    setServiceWarning('')
    setError('')

    cloud.regions(cloudProvider)
      .then(({ regions }) => {
        setAllRegions(regions)
        setSelectedRegions(regions.slice(0, 4))
      })
      .catch(() => setAllRegions([]))
      .finally(() => setLoadingRegions(false))

    cloud.services(cloudProvider)
      .then(({ services: svcs }) => {
        setServices(svcs)
        setSelectedServices(svcs.map((s) => s.id))
      })
      .catch(() => {
        setServiceWarning('Could not load service list — using defaults.')
        setSelectedServices(['ec2', 'rds', 's3', 'lambda'])
      })
      .finally(() => setLoadingServices(false))
  }, [cloudProvider])

  // Load org accounts when Organizations tab is active
  const loadOrgAccounts = useCallback(async () => {
    setLoadingOrg(true)
    setOrgError('')
    try {
      const { accounts } = await awsApi.accounts()
      setOrgAccounts(accounts)
    } catch (e: unknown) {
      setOrgError(e instanceof Error ? e.message : 'Failed to load accounts')
    } finally {
      setLoadingOrg(false)
    }
  }, [])

  useEffect(() => {
    if (cloudProvider === 'aws' && awsAuthMode === 'organizations') loadOrgAccounts()
  }, [cloudProvider, awsAuthMode, loadOrgAccounts])

  const toggleOrgAccount = (id: string) =>
    updatePrefs({
      selectedOrgAccountIds: selectedOrgAccountIds.includes(id)
        ? selectedOrgAccountIds.filter((x) => x !== id)
        : [...selectedOrgAccountIds, id],
    })

  const handleAddOrgAccount = async () => {
    if (!newOrgId.trim() || addingOrg) return
    if (!ACCOUNT_ID_RE.test(newOrgId.trim())) { setAddOrgError('Account ID must be exactly 12 digits.'); return }
    setAddOrgError('')
    setAddingOrg(true)
    try {
      const { account } = await awsApi.addAccount({ account_id: newOrgId.trim(), name: newOrgName.trim() || newOrgId.trim() })
      setOrgAccounts((prev) => [...prev, account])
      updatePrefs({ selectedOrgAccountIds: [...new Set([...selectedOrgAccountIds, account.account_id])] })
      setNewOrgId(''); setNewOrgName(''); setShowAddOrg(false)
    } catch (e: unknown) {
      setAddOrgError(e instanceof Error ? e.message : 'Failed to add account')
    } finally {
      setAddingOrg(false)
    }
  }

  const handleRemoveOrgAccount = async (id: string) => {
    try {
      await awsApi.removeAccount(id)
      setOrgAccounts((prev) => prev.filter((a) => a.account_id !== id))
      updatePrefs({ selectedOrgAccountIds: selectedOrgAccountIds.filter((x) => x !== id) })
    } catch { /* ignore */ }
  }

  const handleRun = async () => {
    setError('')
    if (selectedRegions.length === 0) { setError('Select at least one region.'); return }
    if (selectedServices.length === 0) { setError('Select at least one service.'); return }

    if (cloudProvider === 'aws') {
      if (awsAuthMode === 'sso' && ssoCreds.length === 0) {
        setError('No SSO session found. Choose the AWS SSO tab and log in.'); return
      }
      if (awsAuthMode === 'organizations' && selectedOrgAccountIds.length === 0) {
        setError('Select at least one account in the Organizations tab.'); return
      }
      if (awsAuthMode === 'keys' && (!awsAccessKeyId.trim() || !awsSecretAccessKey.trim())) {
        setError('Enter your AWS Access Key ID and Secret Access Key.'); return
      }
    }
    if (cloudProvider === 'azure' && !subscriptionId.trim()) {
      setError('Enter your Azure Subscription ID.'); return
    }
    if (cloudProvider === 'gcp' && !projectId.trim()) {
      setError('Enter your GCP Project ID.'); return
    }

    const payload = {
      cloud_provider: cloudProvider,
      regions: selectedRegions,
      services: selectedServices,
      // AWS
      aws_access_key_id:     cloudProvider === 'aws' && awsAuthMode === 'keys' ? (awsAccessKeyId.trim() || undefined) : undefined,
      aws_secret_access_key: cloudProvider === 'aws' && awsAuthMode === 'keys' ? (awsSecretAccessKey.trim() || undefined) : undefined,
      sso_credentials:       cloudProvider === 'aws' && awsAuthMode === 'sso' ? ssoCreds : undefined,
      accounts:              cloudProvider === 'aws' && awsAuthMode === 'organizations' ? selectedOrgAccountIds : undefined,
      use_organizations:     cloudProvider === 'aws' && awsAuthMode === 'organizations',
      // Azure
      subscription_id:    cloudProvider === 'azure' ? subscriptionId.trim() : undefined,
      azure_tenant_id:    cloudProvider === 'azure' ? (azureTenantId.trim() || undefined) : undefined,
      azure_client_id:    cloudProvider === 'azure' ? (azureClientId.trim() || undefined) : undefined,
      azure_client_secret: cloudProvider === 'azure' ? (azureClientSecret.trim() || undefined) : undefined,
      // GCP
      project_id: cloudProvider === 'gcp' ? projectId.trim() : undefined,
      gcp_api_key: cloudProvider === 'gcp' ? (gcpApiKey.trim() || undefined) : undefined,
      // AI
      ai_provider: aiProvider || undefined,
      ai_api_key:  aiApiKey.trim() || undefined,
    }

    setValidating(true)
    try {
      await analysis.validate({
        cloud_provider:       payload.cloud_provider,
        subscription_id:      payload.subscription_id,
        azure_tenant_id:      payload.azure_tenant_id,
        azure_client_id:      payload.azure_client_id,
        azure_client_secret:  payload.azure_client_secret,
        project_id:           payload.project_id,
        use_organizations:    payload.use_organizations,
        accounts:             payload.accounts,
        aws_access_key_id:    payload.aws_access_key_id,
        aws_secret_access_key: payload.aws_secret_access_key,
        sso_credentials:      payload.sso_credentials,
        gcp_api_key:          payload.gcp_api_key,
        ai_provider:          payload.ai_provider,
        ai_api_key:           payload.ai_api_key,
      })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Validation failed')
      setValidating(false)
      return
    }
    setValidating(false)

    setLaunching(true)
    try {
      const { analysis_id } = await analysis.start(payload)
      navigate(`/analyze/${analysis_id}`)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to start analysis')
      setLaunching(false)
    }
  }

  const meta = PROVIDER_META[cloudProvider]

  return (
    <div className="max-w-3xl mx-auto px-4 py-8 space-y-5">

      {/* ── Header ────────────────────────────────────────────────── */}
      <div style={{ borderLeft: '3px solid #6366f1', paddingLeft: '14px' }}>
        <h1 className="text-2xl font-bold text-white" style={{ letterSpacing: '-0.02em' }}>Cost Analysis</h1>
        <p className="text-sm mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
          Detect over-provisioning, unused resources &amp; misconfigurations
        </p>
      </div>

      {/* ── Cloud Provider Selector ────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center gap-2 mb-4">
          <Cloud size={14} style={{ color: 'var(--color-text-tertiary)' }} />
          <h2 className="font-semibold text-white text-sm" style={{ letterSpacing: '0.01em' }}>Cloud Provider</h2>
        </div>
        <div className="grid grid-cols-3 gap-3">
          {(Object.keys(PROVIDER_META) as CloudProvider[]).map((p) => {
            const m = PROVIDER_META[p]
            const active = cloudProvider === p
            return (
              <button
                key={p}
                onClick={() => { updatePrefs({ cloudProvider: p }); setError('') }}
                className="flex flex-col items-center gap-2 py-4 rounded-xl font-semibold text-sm"
                style={{
                  /* inactive: tiny brand tint so each provider is visually distinct at a glance */
                  background: active ? m.bg : `${m.color}18`,
                  border: `2px solid ${active ? m.border : m.color + '55'}`,
                  transform: active ? 'scale(1.04)' : 'scale(1)',
                  boxShadow: active ? `0 6px 20px ${m.color}50` : 'none',
                  transition: 'all 0.18s ease',
                }}
              >
                {/* icon: full brand color, dimmed via opacity when inactive */}
                <span style={{ opacity: active ? 1 : 0.42 }}>
                  <ProviderIcon provider={p} color={m.color} />
                </span>
                {/* label: brand color when active, muted when inactive */}
                <span style={{ color: active ? m.color : 'var(--color-text-secondary)', fontWeight: active ? 700 : 500 }}>
                  {m.label}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* ── AWS Credentials ───────────────────────────────────────── */}
      {cloudProvider === 'aws' && (
        <div className="card space-y-4">
          <h2 className="font-medium text-white text-sm">AWS Credentials</h2>

          {/* Auth mode tabs */}
          <div className="grid grid-cols-3 gap-1.5 rounded-xl p-1" style={{ background: 'var(--color-section-bg)' }}>
            {([
              { id: 'keys' as const,          label: 'Access Keys',   Icon: Key },
              { id: 'sso' as const,           label: 'AWS SSO',       Icon: Users },
              { id: 'organizations' as const, label: 'Organizations', Icon: Building2 },
            ]).map(({ id, label, Icon }) => (
              <button
                key={id}
                type="button"
                onClick={() => { updatePrefs({ awsAuthMode: id }); setError('') }}
                className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs font-medium transition-all"
                style={{
                  background: awsAuthMode === id ? 'rgba(255,153,0,0.2)' : 'transparent',
                  border:     awsAuthMode === id ? '1px solid rgba(255,153,0,0.6)' : '1px solid transparent',
                  color:      awsAuthMode === id ? 'var(--color-text)' : 'var(--color-text-secondary)',
                }}>
                <Icon size={13} style={{ color: awsAuthMode === id ? '#FF9900' : 'var(--color-text-tertiary)' }} />
                {label}
              </button>
            ))}
          </div>

          {/* Access Keys */}
          {awsAuthMode === 'keys' && (
            <div className="space-y-3 rounded-lg p-4" style={{ background: 'var(--color-section-bg)', border: '1px solid rgba(165,180,252,0.2)' }}>
              <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
                Kept in browser only — sent to backend during scan, never stored in database.
              </p>
              <div>
                <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                  Access Key ID <span style={{ color: '#f87171' }}>*</span>
                </label>
                <input
                  className="input w-full text-sm font-mono"
                  placeholder="AKIAIOSFODNN7EXAMPLE"
                  value={awsAccessKeyId}
                  onChange={(e) => updatePrefs({ awsAccessKeyId: e.target.value })}
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
                  onChange={(e) => updatePrefs({ awsSecretAccessKey: e.target.value })}
                  autoComplete="new-password"
                />
              </div>
            </div>
          )}

          {/* AWS SSO */}
          {awsAuthMode === 'sso' && (
            <SSOAuth
              onComplete={(creds) => setSsoCreds(creds)}
              onCancel={() => updatePrefs({ awsAuthMode: 'keys' })}
            />
          )}

          {/* Organizations (server-side SSO profiles) */}
          {awsAuthMode === 'organizations' && (
            <div className="space-y-3">
              <div className="rounded-lg p-3 text-xs leading-relaxed"
                style={{ background: 'rgba(165,180,252,0.07)', border: '1px solid rgba(165,180,252,0.2)', color: 'var(--color-text-secondary)' }}>
                Uses server-side SSO profiles from <code style={{ color: '#a5b4fc' }}>~/.aws/config</code>.
                Run <code style={{ color: '#86efac' }}>aws sso login</code> on the server host first.
              </div>

              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-white">
                  Accounts{' '}
                  <span style={{ color: 'var(--color-text-tertiary)' }}>({selectedOrgAccountIds.length} selected)</span>
                </span>
                <div className="flex items-center gap-3">
                  <button type="button" onClick={loadOrgAccounts} disabled={loadingOrg}
                    className="flex items-center gap-1 text-xs disabled:opacity-50" style={{ color: 'var(--color-text-secondary)' }}>
                    <RefreshCw size={11} className={loadingOrg ? 'animate-spin' : ''} /> Refresh
                  </button>
                  <button type="button" onClick={() => { setShowAddOrg((v) => !v); setAddOrgError('') }}
                    className="flex items-center gap-1 text-xs" style={{ color: '#a5b4fc' }}>
                    <Plus size={11} /> Add
                  </button>
                </div>
              </div>

              {orgError && (
                <p className="text-xs flex items-center gap-1" style={{ color: '#f87171' }}>
                  <AlertTriangle size={12} className="shrink-0" /> {orgError}
                </p>
              )}

              {showAddOrg && (
                <div className="rounded-lg p-3 space-y-2" style={{ background: 'var(--color-section-bg)', border: '1px solid rgba(255,153,0,0.3)' }}>
                  <div className="flex gap-2">
                    <input className="input flex-1 text-sm font-mono" placeholder="Account ID (12 digits)"
                      value={newOrgId} onChange={(e) => setNewOrgId(e.target.value)} maxLength={12} />
                    <input className="input flex-1 text-sm" placeholder="Display name (optional)"
                      value={newOrgName} onChange={(e) => setNewOrgName(e.target.value)} />
                  </div>
                  {addOrgError && <p className="text-red-400 text-xs">{addOrgError}</p>}
                  <div className="flex gap-2 justify-end">
                    <button type="button" onClick={() => { setShowAddOrg(false); setAddOrgError(''); setNewOrgId(''); setNewOrgName('') }}
                      className="btn-ghost text-xs px-3 py-1">Cancel</button>
                    <button type="button" onClick={handleAddOrgAccount} disabled={!newOrgId.trim() || addingOrg}
                      className="btn-primary text-xs px-3 py-1 flex items-center gap-1">
                      {addingOrg && <RefreshCw size={10} className="animate-spin" />}
                      {addingOrg ? 'Adding…' : 'Add'}
                    </button>
                  </div>
                </div>
              )}

              <div className="space-y-1 max-h-48 overflow-y-auto">
                {loadingOrg && (
                  <p className="text-xs py-2 flex items-center gap-1" style={{ color: 'var(--color-text-tertiary)' }}>
                    <RefreshCw size={12} className="animate-spin" /> Loading accounts…
                  </p>
                )}
                {!loadingOrg && orgAccounts.length === 0 && (
                  <p className="text-xs py-2" style={{ color: 'var(--color-text-tertiary)' }}>
                    No accounts found. Click Refresh or Add to configure accounts.
                  </p>
                )}
                {orgAccounts.map((acct) => {
                  const sel = selectedOrgAccountIds.includes(acct.account_id)
                  return (
                    <div key={acct.account_id}
                      className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs cursor-pointer transition-all"
                      style={{
                        background: sel ? 'rgba(255,153,0,0.12)' : 'var(--color-section-bg)',
                        border: sel ? '1px solid rgba(255,153,0,0.5)' : '1px solid var(--color-section-border)',
                        color: sel ? 'var(--color-text)' : 'var(--color-text-secondary)',
                      }}
                      onClick={() => toggleOrgAccount(acct.account_id)}>
                      <input type="checkbox" className="shrink-0" checked={sel}
                        onChange={() => {}} onClick={(e) => e.stopPropagation()} />
                      <span className="font-mono">{acct.account_id}</span>
                      <span className="flex-1 truncate" style={{ color: 'var(--color-text-secondary)' }}>{acct.name}</span>
                      <button type="button" onClick={(e) => { e.stopPropagation(); handleRemoveOrgAccount(acct.account_id) }}
                        className="ml-auto shrink-0 transition-colors" style={{ color: 'var(--color-text-tertiary)' }}
                        onMouseEnter={(e) => (e.currentTarget as HTMLElement).style.color = '#f87171'}
                        onMouseLeave={(e) => (e.currentTarget as HTMLElement).style.color = 'var(--color-text-tertiary)'}>
                        <Trash2 size={12} />
                      </button>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Azure Credentials ─────────────────────────────────────── */}
      {cloudProvider === 'azure' && (
        <div className="card space-y-4">
          <h2 className="font-medium text-white text-sm">Azure Credentials</h2>
          <div>
            <label className="block text-xs mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
              Subscription ID <span style={{ color: '#f87171' }}>*</span>
            </label>
            <input className="input w-full text-sm font-mono"
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              value={subscriptionId}
              onChange={(e) => updatePrefs({ subscriptionId: e.target.value })} />
          </div>
          <div className="rounded-lg p-4 space-y-3" style={{ background: 'var(--color-section-bg)', border: '1px solid rgba(0,120,212,0.3)' }}>
            <p className="text-xs font-medium" style={{ color: 'var(--color-text-secondary)' }}>
              Service Principal <span className="font-normal" style={{ color: 'var(--color-text-tertiary)' }}>(optional — leave blank to use DefaultAzureCredential)</span>
            </p>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Tenant ID</label>
              <input className="input w-full text-sm font-mono" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={azureTenantId} onChange={(e) => updatePrefs({ azureTenantId: e.target.value })} autoComplete="off" />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Client ID (App ID)</label>
              <input className="input w-full text-sm font-mono" placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
                value={azureClientId} onChange={(e) => updatePrefs({ azureClientId: e.target.value })} autoComplete="off" />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Client Secret</label>
              <input type="password" className="input w-full text-sm font-mono" placeholder="your-client-secret"
                value={azureClientSecret} onChange={(e) => updatePrefs({ azureClientSecret: e.target.value })} autoComplete="new-password" />
            </div>
          </div>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
            Leave Service Principal blank to use <code style={{ color: '#60a5fa' }}>DefaultAzureCredential</code> (Azure CLI, managed identity, or env credentials).
          </p>
        </div>
      )}

      {/* ── GCP Credentials ───────────────────────────────────────── */}
      {cloudProvider === 'gcp' && (
        <div className="card space-y-3">
          <h2 className="font-medium text-white text-sm">GCP Credentials</h2>
          <div>
            <label className="block text-xs mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
              Project ID <span style={{ color: '#f87171' }}>*</span>
            </label>
            <input className="input w-full text-sm font-mono" placeholder="my-gcp-project-id"
              value={projectId} onChange={(e) => updatePrefs({ projectId: e.target.value })} />
          </div>
          <div>
            <label className="block text-xs mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
              Service Account JSON or API Key
              <span className="ml-1.5" style={{ color: 'var(--color-text-tertiary)' }}>(optional — overrides server credentials)</span>
            </label>
            <textarea className="input w-full text-xs font-mono" rows={4}
              placeholder={'{\n  "type": "service_account",\n  "project_id": "...",\n  ...\n}\n\nor paste an API key: AIzaSy...'}
              value={gcpApiKey} onChange={(e) => updatePrefs({ gcpApiKey: e.target.value })}
              style={{ resize: 'vertical', minHeight: '80px' }} />
          </div>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--color-text-tertiary)' }}>
            Paste a service account JSON key, or an API key starting with <code style={{ color: '#60a5fa' }}>AIza</code>.
            Leave blank to use <code style={{ color: '#60a5fa' }}>GOOGLE_APPLICATION_CREDENTIALS</code>.
          </p>
        </div>
      )}

      {/* ── Region Selector ───────────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-medium text-white">
            {cloudProvider === 'azure' ? 'Azure Locations' : cloudProvider === 'gcp' ? 'GCP Regions' : 'AWS Regions'} to scan
            <span className="ml-2 text-xs font-normal" style={{ color: 'var(--color-text-tertiary)' }}>
              ({selectedRegions.length} selected)
            </span>
          </h2>
          <div className="flex gap-2 text-xs">
            <button style={{ color: meta.color + 'cc' }} className="hover:text-white transition-colors"
              onClick={() => setSelectedRegions(allRegions)}>All</button>
            <span style={{ color: 'var(--color-text-tertiary)' }}>|</span>
            <button style={{ color: 'var(--color-text-tertiary)' }} className="hover:text-white transition-colors"
              onClick={() => setSelectedRegions([])}>None</button>
          </div>
        </div>
        {loadingRegions ? (
          <div className="flex items-center gap-2 py-4" style={{ color: 'var(--color-text-tertiary)' }}>
            <RefreshCw size={14} className="animate-spin" />
            <span className="text-xs">Loading regions…</span>
          </div>
        ) : (
          <div className="grid grid-cols-3 gap-2">
            {allRegions.map((r) => {
              const sel = selectedRegions.includes(r)
              return (
                <label key={r}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs cursor-pointer transition-all"
                  style={{
                    background: sel ? meta.bg : 'var(--color-section-bg)',
                    border: `1.5px solid ${sel ? meta.border : 'var(--color-section-border)'}`,
                    color: 'var(--color-text)',
                    fontWeight: sel ? 600 : 400,
                  }}>
                  <input type="checkbox" className="shrink-0" checked={sel}
                    onChange={() => setSelectedRegions((prev) =>
                      prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]
                    )} />
                  {r}
                </label>
              )
            })}
          </div>
        )}
      </div>

      {/* ── Service Selector ──────────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="font-medium text-white">Services to scan</h2>
            {serviceWarning && (
              <p className="text-xs mt-0.5" style={{ color: 'rgba(255,153,0,0.7)' }}>{serviceWarning}</p>
            )}
          </div>
          <div className="flex gap-2 text-xs">
            <button style={{ color: meta.color + 'cc' }} className="hover:text-white transition-colors"
              onClick={() => setSelectedServices(services.map((s) => s.id))}>All</button>
            <span style={{ color: 'var(--color-text-tertiary)' }}>|</span>
            <button style={{ color: 'var(--color-text-tertiary)' }} className="hover:text-white transition-colors"
              onClick={() => setSelectedServices([])}>None</button>
          </div>
        </div>
        {loadingServices ? (
          <div className="flex items-center gap-2 py-4" style={{ color: 'var(--color-text-tertiary)' }}>
            <RefreshCw size={14} className="animate-spin" />
            <span className="text-xs">Loading services…</span>
          </div>
        ) : (
          <ServiceSelector
            label=""
            items={services.length > 0 ? services : [
              { id: 'ec2',    name: 'EC2 + EBS + EIP + NAT', description: 'Compute, storage, IPs, NAT gateways' },
              { id: 'rds',    name: 'RDS Databases',          description: 'Managed databases and snapshots' },
              { id: 's3',     name: 'S3 Storage',             description: 'Object storage buckets (global)' },
              { id: 'lambda', name: 'Lambda Functions',        description: 'Serverless compute' },
            ]}
            selected={selectedServices}
            onChange={setSelectedServices}
            columns={2}
          />
        )}
      </div>

      {/* ── AI Engine ─────────────────────────────────────────────── */}
      <div className="card">
        <div className="flex items-center gap-2 mb-3">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" style={{ color: 'var(--color-text-tertiary)', flexShrink: 0 }}>
            <path d="M12 2a5 5 0 0 1 5 5c0 1.5-.66 2.84-1.7 3.77L17 20H7l1.7-9.23A5 5 0 0 1 7 7a5 5 0 0 1 5-5z"
              stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" fill="none"/>
            <circle cx="12" cy="7" r="1.5" fill="currentColor"/>
          </svg>
          <h2 className="font-medium text-white text-sm">AI Engine</h2>
          <span className="text-xs ml-1" style={{ color: 'var(--color-text-tertiary)' }}>— powers the cost analysis</span>
        </div>
        <div className="space-y-3">
          <div>
            <label className="block text-xs mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>Provider</label>
            <div className="relative">
              <select className="input w-full text-sm"
                value={aiProvider}
                onChange={(e) => updatePrefs({ aiProvider: e.target.value, aiApiKey: '' })}
                style={{ appearance: 'none', paddingRight: '28px', background: 'var(--color-select-bg)', color: 'var(--color-select-text)' }}>
                {AI_PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value} style={{ background: 'var(--color-select-bg)', color: 'var(--color-select-text)' }}>
                    {p.label}
                  </option>
                ))}
              </select>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none"
                className="absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--color-text-tertiary)' }}>
                <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          </div>
          {aiProvider && aiProvider !== 'bedrock' && aiProvider !== 'ollama' && (
            <div>
              <label className="block text-xs mb-1.5" style={{ color: 'var(--color-text-secondary)' }}>
                API Key <span className="ml-1.5" style={{ color: 'var(--color-text-tertiary)' }}>(stored in browser only)</span>
              </label>
              <input type="password" className="input w-full text-sm font-mono"
                placeholder={AI_PROVIDERS.find((p) => p.value === aiProvider)?.placeholder ?? 'API key...'}
                value={aiApiKey}
                onChange={(e) => updatePrefs({ aiApiKey: e.target.value })}
                autoComplete="new-password" />
            </div>
          )}
          {!aiProvider && (
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              Using server-configured key. Set <code style={{ color: '#a5b4fc' }}>ANTHROPIC_API_KEY</code>,{' '}
              <code style={{ color: '#a5b4fc' }}>OPENAI_API_KEY</code>, or <code style={{ color: '#a5b4fc' }}>GOOGLE_API_KEY</code> in the server's <code style={{ color: '#a5b4fc' }}>.env</code>.
            </p>
          )}
          {aiProvider === 'bedrock' && (
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>Uses your existing AWS credentials — no extra key needed.</p>
          )}
          {aiProvider === 'ollama' && (
            <p className="text-xs" style={{ color: 'var(--color-text-tertiary)' }}>
              Connects to local Ollama. Set <code style={{ color: '#a5b4fc' }}>OLLAMA_BASE_URL</code> on the server if not default.
            </p>
          )}
        </div>
      </div>

      {error && (
        <div className="bg-red-900/50 border border-red-700 text-red-300 text-sm rounded-lg px-4 py-2.5">
          {error}
        </div>
      )}

      <button
        onClick={handleRun}
        disabled={launching || validating || loadingServices || loadingRegions}
        className="btn-primary w-full py-3.5 text-base flex items-center justify-center gap-2"
        style={{
          background: (launching || validating) ? undefined : `linear-gradient(135deg, ${meta.color}cc, ${meta.color}88)`,
        }}
      >
        {validating ? (
          <><RefreshCw size={18} className="animate-spin" /> Validating credentials…</>
        ) : launching ? (
          <><RefreshCw size={18} className="animate-spin" /> Starting {PROVIDER_META[cloudProvider].label} analysis…</>
        ) : (
          <><Play size={18} /> Run {PROVIDER_META[cloudProvider].label} Cost Analysis</>
        )}
      </button>
    </div>
  )
}

function ProviderIcon({ provider, color }: { provider: CloudProvider; color: string }) {
  if (provider === 'aws') {
    return (
      <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
        <path d="M12 26c-2.2-1.1-4-3.5-4-6.5 0-4.4 3.6-8 8-8 .7 0 1.4.1 2 .3C19.3 9.7 21.5 8 24 8c3.3 0 6 2.7 6 6 0 .3 0 .7-.1 1C31.7 15.7 33 17.7 33 20c0 3.3-2.7 6-6 6H12z" fill={color} opacity="0.9"/>
        <path d="M11 32l2-4h14l2 4" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
        <path d="M20 28v6" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
      </svg>
    )
  }
  if (provider === 'azure') {
    return (
      <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
        <path d="M16 8l-8 22h6l10-12-8-10z" fill={color} opacity="0.8"/>
        <path d="M22 14l-6 16h16L22 14z" fill={color}/>
      </svg>
    )
  }
  return (
    <svg width="28" height="28" viewBox="0 0 40 40" fill="none">
      <circle cx="20" cy="20" r="10" stroke={color} strokeWidth="2.5" fill="none"/>
      <path d="M20 10v4M20 26v4M10 20h4M26 20h4" stroke={color} strokeWidth="2" strokeLinecap="round"/>
      <circle cx="20" cy="20" r="3" fill={color}/>
    </svg>
  )
}
