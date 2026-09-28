/** 验证统一请求层为浏览器 Session 写请求补齐 CSRF 凭据。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiRequest } from './client'

afterEach(() => {
  vi.unstubAllGlobals()
})

function stubCookie(value: string): void {
  let cookie = value
  vi.stubGlobal('document', {
    get cookie() {
      return cookie
    },
    set cookie(next: string) {
      cookie = next
    },
  })
}

describe('apiRequest CSRF protection', () => {
  it('bootstraps a token for an existing session before sending a write request', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ csrf_token: 'bound-session-token' }), { status: 200 }),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify({ id: 'created' }), { status: 201 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      apiRequest<{ id: string }>('/api/v1/example', { method: 'POST' }),
    ).resolves.toEqual({ id: 'created' })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/v1/auth/csrf')
    const writeOptions = fetchMock.mock.calls[1]?.[1] as RequestInit
    expect(new Headers(writeOptions.headers).get('X-CSRF-Token')).toBe('bound-session-token')
  })

  it('does not bootstrap or attach a session token to login requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/v1/auth/login', { method: 'POST', body: '{}' })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const options = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(options.headers).has('X-CSRF-Token')).toBe(false)
  })

  it('lets an unauthenticated write reach its normal API response after bootstrap 401', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{"detail":"未登录"}', { status: 401 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest('/api/v1/example', { method: 'POST' })).rejects.toThrow('未登录')

    expect(fetchMock).toHaveBeenCalledTimes(2)
    const writeOptions = fetchMock.mock.calls[1]?.[1] as RequestInit
    expect(new Headers(writeOptions.headers).has('X-CSRF-Token')).toBe(false)
  })

  it('reuses the readable CSRF cookie without a bootstrap round trip', async () => {
    stubCookie('ragmanage_csrf=cookie-token')
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/v1/example', { method: 'DELETE' })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const options = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(options.headers).get('X-CSRF-Token')).toBe('cookie-token')
  })

  it('does not attach browser CSRF credentials to explicit Bearer requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/v1/customer/write', {
      method: 'POST',
      headers: { Authorization: 'Bearer customer-key' },
      body: '{}',
    })

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const options = fetchMock.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(options.headers).has('X-CSRF-Token')).toBe(false)
  })
})
