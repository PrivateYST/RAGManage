// @vitest-environment happy-dom
/** 路由表回归测试，防止启动入口重构后遗漏页面或认证布局层级。 */

import { describe, expect, it } from 'vitest'
import { routes } from './index'

describe('application routes', () => {
  // 主要路径必须集中登记在 router 模块，避免 main.ts 与页面导航出现分叉。
  it('keeps the expected public and protected route structure', () => {
    const rootRoute = routes.find((route) => route.path === '/')
    const childPaths = rootRoute?.children?.map((route) => route.path) ?? []

    expect(routes.some((route) => route.path === '/login')).toBe(true)
    expect(rootRoute?.meta?.requiresAuth).toBe(true)
    expect(childPaths).toEqual(
      expect.arrayContaining(['', 'dashboard', 'documents', 'releases', 'chat', 'members']),
    )
  })
})
