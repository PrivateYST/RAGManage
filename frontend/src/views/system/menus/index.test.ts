// @vitest-environment happy-dom
/**
 * 菜单迁移回归：覆盖节点创建/更新/显隐操作，并保护路由与权限标识的不可编辑约束。
 */
import type { MenuRow } from '@/api/admin'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { routeComponents } from '@/router'
import { useMenusPage } from './index'

const api = vi.hoisted(() => ({
  fetchMenus: vi.fn(),
  createMenu: vi.fn(),
  updateMenu: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('@/api/admin', () => ({
  fetchMenus: api.fetchMenus,
  createMenu: api.createMenu,
  updateMenu: api.updateMenu,
}))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: api.success, error: api.error }),
}))

/** 最小菜单数据，用于检查编辑字段和可见性反转请求。 */
function menu(overrides: Partial<MenuRow> = {}): MenuRow {
  return {
    id: 'menu-1',
    code: 'users',
    name: '用户',
    kind: 'menu',
    parent_id: null,
    route: '/system/users',
    icon: null,
    permission_code: 'users:view',
    sort_order: 2,
    visible: true,
    status: 'active',
    ...overrides,
  }
}

describe('menus management migration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchMenus.mockResolvedValue({ items: [menu()] })
    api.createMenu.mockResolvedValue(menu())
    api.updateMenu.mockResolvedValue(menu())
  })

  it('maps the menu route to a dedicated page component', () => {
    expect(routeComponents['/system/menus']).not.toBe(routeComponents['/system/roles'])
  })

  it('creates a menu with numeric parent ID and refreshes the list', async () => {
    const page = useMenusPage()
    const result = await page.submitCreate({
      code: 'reports',
      name: '报表',
      kind: 'menu',
      parent_id: '12',
      route: '/reports',
      icon: 'Chart',
      permission_code: 'reports:view',
      sort_order: 3,
      visible: true,
    })

    expect(result).toBe(true)
    expect(api.createMenu).toHaveBeenCalledWith({
      code: 'reports',
      name: '报表',
      kind: 'menu',
      parent_id: 12,
      route: '/reports',
      icon: 'Chart',
      permission_code: 'reports:view',
      sort_order: 3,
      visible: true,
    })
    expect(api.fetchMenus).toHaveBeenCalledOnce()
  })

  it('preserves the form operation on create failure and reports the error', async () => {
    api.createMenu.mockRejectedValueOnce(new Error('编码已存在'))
    const page = useMenusPage()
    const result = await page.submitCreate({
      code: 'reports',
      name: '报表',
      kind: 'menu',
      parent_id: '',
      route: '',
      icon: '',
      permission_code: 'reports:view',
      sort_order: 0,
      visible: true,
    })

    expect(result).toBe(false)
    expect(api.error).toHaveBeenCalledWith('编码已存在')
    expect(api.fetchMenus).not.toHaveBeenCalled()
  })

  it('updates safe metadata without allowing the route or permission to enter the payload', async () => {
    const page = useMenusPage()
    page.openEditor(menu())
    await page.submitEdit({ name: '账号管理', parent_id: '5', sort_order: 4, status: 'disabled' })

    expect(api.updateMenu).toHaveBeenCalledWith('menu-1', {
      name: '账号管理',
      parent_id: 5,
      sort_order: 4,
      status: 'disabled',
    })
  })

  it('inverts visibility and reloads the menu collection', async () => {
    const page = useMenusPage()

    await page.toggleVisibility(menu())

    expect(api.updateMenu).toHaveBeenCalledWith('menu-1', { visible: false })
    expect(api.success).toHaveBeenCalledWith('菜单已隐藏')
    expect(api.fetchMenus).toHaveBeenCalledOnce()
  })
})
