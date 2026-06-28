import type { AnalysisDetail, AWSAccount, CloudProvider, HistoryItem } from './types'

const BASE = '/api'

// Cache static lists per provider for the session lifetime
const _cachedServices: Partial<Record<CloudProvider, { id: string; name: string; description: string }[]>> = {}
const _cachedRegions: Partial<Record<CloudProvider, string[]>> = {}

async function req<T>(path: string, opts: RequestInit & { skipRedirectOn401?: boolean } = {}): Promise<T> {
  const { skipRedirectOn401, ...fetchOpts } = opts
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, {
      ...fetchOpts,
      credentials: 'include',
      headers: { 'Content-Type': 'application/json', ...(fetchOpts.headers ?? {}) },
    })
  } catch {
    throw new Error('Cannot reach the server. Make sure the backend is running and try again.')
  }
  if (res.status === 401 || res.status === 403) {
    if (!skipRedirectOn401) window.location.href = '/login'
    throw new Error('Session expired — please log in again.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = body.detail
    const msg = typeof detail === 'string'
      ? detail
      : Array.isArray(detail)
        ? detail.map((d: { msg: string }) => d.msg).join('; ')
        : 'Request failed'
    throw new Error(msg)
  }
  return res.json()
}

export const auth = {
  signup: (email: string, password: string) =>
    req<{ user: { id: number; email: string } }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  login: (email: string, password: string) =>
    req<{ user: { id: number; email: string } }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  logout: () =>
    req<{ status: string }>('/auth/logout', { method: 'POST' }),

  me: () =>
    req<{ id: number; email: string }>('/auth/me', { skipRedirectOn401: true }),

  changePassword: (current_password: string, new_password: string) =>
    req<{ message: string }>('/auth/change-password', {
      method: 'POST',
      body: JSON.stringify({ current_password, new_password }),
    }),
}

export const cloud = {
  regions: async (provider: CloudProvider = 'aws') => {
    if (_cachedRegions[provider]) return { regions: _cachedRegions[provider]! }
    const r = await req<{ regions: string[] }>(`/regions?provider=${provider}`)
    _cachedRegions[provider] = r.regions
    return r
  },
  services: async (provider: CloudProvider = 'aws') => {
    if (_cachedServices[provider]) return { services: _cachedServices[provider]! }
    const r = await req<{ services: { id: string; name: string; description: string }[] }>(
      `/services?provider=${provider}`
    )
    _cachedServices[provider] = r.services
    return r
  },
}

export const aws = {
  regions: () => cloud.regions('aws'),
  services: () => cloud.services('aws'),
  accounts: () => req<{ accounts: AWSAccount[] }>('/config/accounts'),
  addAccount: (data: { account_id: string; name: string; email?: string }) =>
    req<{ account: AWSAccount }>('/config/accounts', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  removeAccount: (account_id: string) =>
    req<{ status: string }>(`/config/accounts/${account_id}`, { method: 'DELETE' }),
}

export interface SSOCredential {
  account_id: string
  account_name: string
  role_name: string
  access_key: string
  secret_key: string
  session_token: string
}

const SSO_CREDS_KEY = 'cost_detective_sso_creds'

export function saveSSOCreds(creds: SSOCredential[]): void {
  try { sessionStorage.setItem(SSO_CREDS_KEY, JSON.stringify(creds)) } catch { /* ignore */ }
}

export function loadSSOCreds(): SSOCredential[] | null {
  try {
    const raw = sessionStorage.getItem(SSO_CREDS_KEY)
    if (!raw) return null
    return JSON.parse(raw) as SSOCredential[]
  } catch { return null }
}

export function clearSSOCreds(): void {
  try { sessionStorage.removeItem(SSO_CREDS_KEY) } catch { /* ignore */ }
}

type ScanPayload = {
  cloud_provider: CloudProvider
  regions: string[]
  services: string[]
  accounts?: string[]
  use_organizations?: boolean
  subscription_id?: string
  azure_tenant_id?: string
  azure_client_id?: string
  azure_client_secret?: string
  project_id?: string
  aws_access_key_id?: string
  aws_secret_access_key?: string
  gcp_api_key?: string
  ai_provider?: string
  ai_api_key?: string
  sso_credentials?: SSOCredential[]
}

export const sso = {
  start: (start_url: string, region: string) =>
    req<{
      session_id: string
      user_code: string
      verification_uri: string
      verification_uri_complete: string
      expires_in: number
      interval: number
    }>('/sso/start', { method: 'POST', body: JSON.stringify({ start_url, region }) }),

  poll: (session_id: string) =>
    req<{ status: 'pending' | 'authorized' | 'expired' | 'error'; message?: string }>(
      `/sso/poll/${session_id}`
    ),

  accounts: (session_id: string) =>
    req<{
      accounts: Array<{ account_id: string; account_name: string; email: string; roles: string[] }>
    }>(`/sso/accounts/${session_id}`),

  credentials: (session_id: string, selections: Array<{ account_id: string; account_name: string; role_name: string }>) =>
    req<{ credentials: SSOCredential[]; errors: string[] }>('/sso/credentials', {
      method: 'POST',
      body: JSON.stringify({ session_id, selections }),
    }),
}

export const analysis = {
  validate: (payload: Pick<ScanPayload,
    'cloud_provider' | 'subscription_id' | 'azure_tenant_id' | 'azure_client_id' | 'azure_client_secret' |
    'project_id' | 'use_organizations' | 'accounts' |
    'aws_access_key_id' | 'aws_secret_access_key' | 'gcp_api_key' | 'ai_provider' | 'ai_api_key' |
    'sso_credentials'>) =>
    req<{ ok: boolean; message: string }>('/validate', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  start: (payload: ScanPayload) =>
    req<{ analysis_id: string; status: string }>('/analyze', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  history: (limit = 100, offset = 0) =>
    req<{ analyses: HistoryItem[] }>(`/history?limit=${limit}&offset=${offset}`),

  get: (id: string) => req<AnalysisDetail>(`/history/${id}`),

  delete: (id: string) => req<{ status: string }>(`/history/${id}`, { method: 'DELETE' }),
}
