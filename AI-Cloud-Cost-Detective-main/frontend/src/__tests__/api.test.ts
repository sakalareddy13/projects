import { describe, it, expect, vi, beforeEach } from 'vitest'
import { auth } from '../api'

const mockFetch = vi.fn()
vi.stubGlobal('fetch', mockFetch)

function mockResponse(body: object, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response)
}

beforeEach(() => mockFetch.mockReset())

describe('auth.login', () => {
  it('sends credentials and returns user', async () => {
    mockFetch.mockReturnValueOnce(mockResponse({ user: { id: 1, email: 'a@b.com' } }))
    const result = await auth.login('a@b.com', 'pass')
    expect(result.user.email).toBe('a@b.com')
    const [url, opts] = mockFetch.mock.calls[0]
    expect(url).toBe('/api/auth/login')
    expect((opts as RequestInit).credentials).toBe('include')
  })

  it('throws on 401', async () => {
    // Redirect mock — location change is no-op in jsdom
    mockFetch.mockReturnValueOnce(mockResponse({ detail: 'Invalid email or password' }, 401))
    await expect(auth.login('x@x.com', 'wrong')).rejects.toThrow()
  })
})

describe('auth.me', () => {
  it('sends include credentials', async () => {
    mockFetch.mockReturnValueOnce(mockResponse({ id: 2, email: 'me@x.com' }))
    await auth.me()
    const [, opts] = mockFetch.mock.calls[0]
    expect((opts as RequestInit).credentials).toBe('include')
  })
})
