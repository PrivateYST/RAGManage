// @vitest-environment happy-dom
/**
 * 角色管理迁移回归：系统角色必须保持不可变，自定义角色同步当前菜单并反馈结果。
 */
import type { MenuRow, RoleRow } from '@/api/admin'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { routeComponents } from '@/router'
import { useRolesPage } from './index'

const api = vi.hoisted(() => ({
  fetchRoles: vi.fn(),
  fetchMenus: vi.fn(),
  updateRoleMenus: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('@/api/admin', () => ({
  fetchRoles: api.fetchRoles,
  fetchMenus: api.fetchMenus,
  updateRoleMenus: api.updateRoleMenus,
}))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: api.success, error: api.error }),
}))

/** 最小角色数据，避免测试依赖后端种子数据。 */
function role(overrides: Partial<RoleRow> = {}): RoleRow {
  return {
    id: 'role-1',
    code: 'operator',
    name: '运营',
    scope: 'platform',
    description: '',
    is_system: false,
    menu_ids: [],
    ...overrides,
  }
}

/** 当前菜单契约的最小实例，用于验证同步使用最新的服务端集合。 */
function menu(id: string): MenuRow {
  return {
    id,
    code: id,
    name: id,
    kind: 'menu',
    parent_id: null,
    route: '/example',
    icon: null,
    permission_code: `${id}:view`,
    sort_order: 1,
    visible: true,
    status: 'active',
  }
}

describe('roles management migration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchRoles.mockResolvedValue({ items: [role()] })
    api.fetchMenus.mockResolvedValue({ items: [menu('menu-a'), menu('menu-b')] })
    api.updateRoleMenus.mockResolvedValue(role())
  })

  it('uses a page component separate from spaces and users', () => {
    expect(routeComponents['/system/roles']).not.toBe(routeComponents['/system/spaces'])
    expect(routeComponents['/system/roles']).not.toBe(routeComponents['/system/users'])
  })

  it('loads roles and retains a retryable error on failure', async () => {
    api.fetchRoles.mockRejectedValueOnce(new Error('服务不可用'))
    const page = useRolesPage()

    await page.loadRoles()

    expect(page.loadError.value).toBe('服务不可用')
    expect(api.error).toHaveBeenCalledWith('服务不可用')
  })

  it('protects built-in roles without issuing a permission update', async () => {
    const page = useRolesPage()

    await page.syncRoleMenus(role({ is_system: true }))

    expect(api.updateRoleMenus).not.toHaveBeenCalled()
    expect(api.error).toHaveBeenCalledWith('系统角色权限由平台初始化维护，不能直接修改')
  })

  it('syncs custom roles against the current menu collection and reloads roles', async () => {
    const page = useRolesPage()

    await page.syncRoleMenus(role())

    expect(api.updateRoleMenus).toHaveBeenCalledWith('role-1', ['menu-a', 'menu-b'])
    expect(api.success).toHaveBeenCalledWith('角色权限已更新')
    expect(api.fetchRoles).toHaveBeenCalledOnce()
  })
})
