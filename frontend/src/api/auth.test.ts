/** 验证会话 API 使用认证会话路由，并对撤销 ID 做路径编码。 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { listSessions, revokeSession } from './auth'

const apiMocks = vi.hoisted(() => ({ apiRequest: vi.fn() }))

vi.mock('./client', () => ({ apiRequest: apiMocks.apiRequest }))

afterEach(() => vi.clearAllMocks())

describe('auth session API', () => {
  it('loads the current account session list', async () => {
    const result = { items: [] }
    apiMocks.apiRequest.mockResolvedValue(result)

    await expect(listSessions()).resolves.toBe(result)
    expect(apiMocks.apiRequest).toHaveBeenCalledWith('/api/v1/auth/sessions')
  })

  it('revokes the selected session with a DELETE request', async () => {
    apiMocks.apiRequest.mockResolvedValue(undefined)

    await revokeSession('session/32')

    expect(apiMocks.apiRequest).toHaveBeenCalledWith('/api/v1/auth/sessions/session%2F32', {
      method: 'DELETE',
    })
  })
})
