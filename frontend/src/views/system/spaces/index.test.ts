// @vitest-environment happy-dom
/**
 * 客户空间页面回归测试：验证路由隔离及医院 Key 操作的业务门槛不被迁移破坏。
 */
import type { TenantRow } from '@/api/admin'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { routeComponents } from '@/router'
import { useSpacesPage } from './index'

const api = vi.hoisted(() => ({
  fetchTenants: vi.fn(),
  createTenant: vi.fn(),
  createApiKey: vi.fn(),
  fetchApiKeyPlaintext: vi.fn(),
  copyText: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  refreshContext: vi.fn(),
  setActiveSpace: vi.fn(),
  user: { platform_role: 'platform_admin' as string | null },
}))

vi.mock('@/api/admin', () => ({
  fetchTenants: api.fetchTenants,
  createTenant: api.createTenant,
}))
vi.mock('@/api/apiKeys', () => ({
  createApiKey: api.createApiKey,
  fetchApiKeyPlaintext: api.fetchApiKeyPlaintext,
}))
vi.mock('@/utils/clipboard', () => ({ copyText: api.copyText }))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: api.success, error: api.error }),
}))
vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    user: api.user,
    refreshContext: api.refreshContext,
    setActiveSpace: api.setActiveSpace,
  }),
}))

/** 最小空间响应，明确区分是否允许创建或读取完整 Key。 */
function tenant(overrides: Partial<TenantRow> = {}): TenantRow {
  return {
    id: '7',
    code: 'hospital-a',
    name: '医院 A',
    status: 'active',
    member_count: 2,
    knowledge_base_count: 1,
    created_at: '2026-01-01T00:00:00Z',
    api_key_id: null,
    api_key_status: null,
    api_key_prefix: null,
    api_key_token_limit: null,
    api_key_token_used: null,
    api_key_token_remaining: null,
    api_key_configured_at: null,
    api_key_expires_at: null,
    ...overrides,
  }
}

describe('customer spaces migration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.user.platform_role = 'platform_admin'
    api.fetchTenants.mockResolvedValue({ items: [] })
    api.createTenant.mockResolvedValue(tenant())
    api.refreshContext.mockResolvedValue(undefined)
    api.createApiKey.mockResolvedValue({ raw_key: 'secret' })
    api.fetchApiKeyPlaintext.mockResolvedValue({ raw_key: 'secret' })
    api.copyText.mockResolvedValue(undefined)
  })

  it('maps spaces to a dedicated route component', () => {
    expect(routeComponents['/system/spaces']).not.toBe(routeComponents['/system/roles'])
  })

  it('refreshes auth context and selects the new space after creation', async () => {
    const page = useSpacesPage()

    await expect(page.createSpace({ code: 'Hospital-A', name: '医院 A' })).resolves.toBe(true)

    expect(api.createTenant).toHaveBeenCalledWith({ code: 'hospital-a', name: '医院 A' })
    expect(api.refreshContext).toHaveBeenCalledOnce()
    expect(api.setActiveSpace).toHaveBeenCalledWith('7')
    expect(api.fetchTenants).toHaveBeenCalledOnce()
  })

  it('keeps the form path usable and exposes a retryable error when loading fails', async () => {
    api.fetchTenants.mockRejectedValueOnce(new Error('网络不可用'))
    const page = useSpacesPage()

    await page.loadTenants()

    expect(page.loadError.value).toBe('网络不可用')
    expect(api.error).toHaveBeenCalledWith('网络不可用')
  })

  it('only opens key setup for active spaces without an assigned key', () => {
    const page = useSpacesPage()

    page.openKeyDialog(tenant({ status: 'disabled' }))
    expect(page.tenantKeyDialogOpen.value).toBe(false)
    page.openKeyDialog(tenant({ api_key_id: 'key-1' }))
    expect(page.tenantKeyDialogOpen.value).toBe(false)
    page.openKeyDialog(tenant())
    expect(page.tenantKeyDialogOpen.value).toBe(true)
  })

  it('lets a space administrator confirm an assigned key but never generate one', () => {
    api.user.platform_role = null
    const page = useSpacesPage()

    page.openKeyDialog(tenant({ api_key_id: 'assigned-key' }))

    expect(page.isPlatformAdmin).toBe(false)
    expect(page.tenantKeyDialogOpen.value).toBe(true)
    expect(api.createApiKey).not.toHaveBeenCalled()
  })

  it('reads and copies a full key only after an explicit request', async () => {
    const page = useSpacesPage()

    await page.copyTenantKey(tenant({ api_key_id: 'key-1' }))

    expect(api.fetchApiKeyPlaintext).toHaveBeenCalledWith('key-1')
    expect(api.copyText).toHaveBeenCalledWith('secret')
    expect(api.success).toHaveBeenCalled()
  })
})
