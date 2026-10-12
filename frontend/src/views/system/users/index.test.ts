// @vitest-environment happy-dom

/**
 * 用户管理页面运行时回归：确保路由挂载时同时读取用户列表和医院选项，避免空表被误认为无账号。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import UserManagementPage from './index.vue'

const api = vi.hoisted(() => ({
  fetchUsers: vi.fn(),
  fetchTenants: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('@/api/admin', () => ({
  fetchUsers: api.fetchUsers,
  fetchTenants: api.fetchTenants,
  updateUser: vi.fn(),
}))

vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ error: api.toastError, success: api.toastSuccess }),
}))

describe('user management page', () => {
  beforeEach(() => {
    api.fetchUsers.mockReset().mockResolvedValue({
      items: [
        {
          id: 'user-1',
          login: 'admin',
          display_name: '平台管理员',
          status: 'active',
          platform_role: 'platform_admin',
          space_count: 1,
          last_login_at: null,
          created_at: '2026-10-12T00:00:00Z',
        },
      ],
    })
    api.fetchTenants.mockReset().mockResolvedValue({ items: [] })
    api.toastError.mockReset()
    api.toastSuccess.mockReset()
  })

  it('loads the user list and hospital options independently on mount', async () => {
    mount(UserManagementPage, { global: { stubs: ['AppTable'] } })
    await flushPromises()

    expect(api.fetchUsers).toHaveBeenCalledOnce()
    expect(api.fetchTenants).toHaveBeenCalledOnce()
  })
})
