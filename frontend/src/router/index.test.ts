// @vitest-environment happy-dom
/**
 * 动态路由回归测试：验证菜单注册、权限过滤、重复清理和刷新时的守卫行为。
 * 这些用例防止业务路由重新硬编码，或在退出/刷新后意外暴露旧菜单。
 */
import type { MenuItem } from '@/api/auth'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'

import { createAppRouter, createDynamicRouteManager, routeComponents, routes } from './index'

const authState = vi.hoisted(() => ({
  value: {
    isAuthenticated: false,
    menus: [] as MenuItem[],
    initialize: vi.fn(async () => undefined),
  },
}))

vi.mock('@/store/auth', () => ({
  useAuthStore: () => authState.value,
}))

function menu(overrides: Partial<MenuItem> = {}): MenuItem {
  return {
    id: 'menu-dashboard',
    code: 'dashboard',
    name: '工作台',
    kind: 'menu',
    parent_id: null,
    route: '/dashboard',
    icon: 'LayoutDashboard',
    permission_code: 'dashboard:view',
    sort_order: 1,
    visible: true,
    ...overrides,
  }
}

describe('dynamic application routes', () => {
  beforeEach(() => {
    authState.value = {
      isAuthenticated: false,
      menus: [],
      initialize: vi.fn(async () => undefined),
    }
  })

  it('keeps only public and layout routes static', () => {
    const rootRoute = routes.find((route) => route.path === '/')

    expect(routes.map((route) => route.path)).toEqual(
      expect.arrayContaining(['/login', '/404', '/', '/:pathMatch(.*)*']),
    )
    expect(rootRoute?.children).toEqual([])
    expect(routeComponents['/dashboard']).toBeDefined()
  })

  it('registers visible menu routes and ignores buttons, hidden items, and unknown paths', () => {
    const router = createAppRouter(createMemoryHistory())
    const manager = createDynamicRouteManager(router)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)

    manager.register([
      menu(),
      menu({ id: 'button-build', kind: 'button', route: '/releases' }),
      menu({ id: 'hidden-chat', route: '/chat', visible: false }),
      menu({ id: 'unknown', route: '/unknown' }),
    ])

    expect(router.hasRoute('dynamic:menu-dashboard')).toBe(true)
    expect(router.hasRoute('dynamic:button-build')).toBe(false)
    expect(router.hasRoute('dynamic:hidden-chat')).toBe(false)
    expect(manager.hasPath('/dashboard')).toBe(true)
    expect(manager.hasPath('/unknown')).toBe(false)
    expect(warn).toHaveBeenCalledWith('[router] ignore unsupported menu route: /unknown')
    warn.mockRestore()
  })

  it('clears old routes before registering a new menu set', () => {
    const router = createAppRouter(createMemoryHistory())
    const manager = createDynamicRouteManager(router)

    manager.register([menu()])
    manager.register([menu({ id: 'menu-chat', route: '/chat', name: '问答' })])

    expect(router.hasRoute('dynamic:menu-dashboard')).toBe(false)
    expect(router.hasRoute('dynamic:menu-chat')).toBe(true)
    expect(manager.hasPath('/dashboard')).toBe(false)
    expect(manager.hasPath('/chat')).toBe(true)
  })

  it('restores a refreshed dynamic route after session initialization', async () => {
    authState.value = {
      isAuthenticated: true,
      menus: [menu()],
      initialize: vi.fn(async () => undefined),
    }
    const router = createAppRouter(createMemoryHistory())

    await router.push('/dashboard')

    expect(router.currentRoute.value.path).toBe('/dashboard')
    expect(router.currentRoute.value.meta.dynamic).toBe(true)
  })

  it('redirects unauthenticated users and preserves the intended path', async () => {
    const router = createAppRouter(createMemoryHistory())

    await router.push('/dashboard')

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/dashboard')
  })

  it('sends authenticated users without a menu to 404', async () => {
    authState.value = {
      isAuthenticated: true,
      menus: [menu({ route: '/chat', id: 'menu-chat', name: '问答' })],
      initialize: vi.fn(async () => undefined),
    }
    const router = createAppRouter(createMemoryHistory())

    await router.push('/dashboard')

    expect(router.currentRoute.value.path).toBe('/404')
  })

  it('redirects authenticated users from login to the first accessible menu', async () => {
    authState.value = {
      isAuthenticated: true,
      menus: [menu({ route: '/chat', id: 'menu-chat', name: '问答' })],
      initialize: vi.fn(async () => undefined),
    }
    const router = createAppRouter(createMemoryHistory())

    await router.push('/login')

    expect(router.currentRoute.value.path).toBe('/chat')
  })
})
