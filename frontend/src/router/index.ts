/**
 * 应用路由模块：维护公开页面、工作台布局和接口菜单驱动的业务路由。
 *
 * 后端返回的菜单只携带路径与权限元数据，组件映射仍由前端维护，避免服务端
 * 任意字符串被当作可执行模块加载。业务路由在登录态恢复后注册，退出登录时清理。
 */
/* eslint-disable style/arrow-parens */
import type { Component } from 'vue'
import type { RouteLocationRaw, Router, RouteRecordRaw, RouterHistory } from 'vue-router'
import type { MenuItem } from '@/api/auth'
import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '@/layouts/AppShell.vue'
import { useAuthStore } from '@/store/auth'
import AuditPage from '@/views/audit/index.vue'
import BuildsPage from '@/views/builds/index.vue'
import ChatPage from '@/views/chat/index.vue'
import DashboardPage from '@/views/dashboard/index.vue'
import DocumentsPage from '@/views/documents/index.vue'
import LoginPage from '@/views/login/index.vue'
import ManagementPage from '@/views/management/index.vue'
import MembersPage from '@/views/members/index.vue'
import ModelsPage from '@/views/models/index.vue'
import NotFoundPage from '@/views/not-found/index.vue'
import SearchTestPage from '@/views/search-test/index.vue'
import TasksPage from '@/views/tasks/index.vue'

const APP_SHELL_ROUTE_NAME = 'app-shell'
const LOGIN_PATH = '/login'
const NOT_FOUND_PATH = '/404'
/** 路径来自数据库，两个表达式分别统一反斜杠和末尾斜杠，且在请求间复用。 */
const BACKSLASH_PATTERN = /\\/g
const TRAILING_SLASH_PATTERN = /\/+$/

/** 后端 route 到本地页面组件的白名单，防止任意接口值参与模块加载。 */
export const routeComponents: Record<string, Component> = {
  '/dashboard': DashboardPage,
  '/knowledge-bases': ManagementPage,
  '/documents': DocumentsPage,
  '/releases': BuildsPage,
  '/chat': ChatPage,
  '/search-test': SearchTestPage,
  '/tasks': TasksPage,
  '/members': MembersPage,
  '/system/spaces': ManagementPage,
  '/system/users': ManagementPage,
  '/system/roles': ManagementPage,
  '/system/menus': ManagementPage,
  '/system/audit': AuditPage,
  '/system/models': ModelsPage,
}

/** 只有登录、404 和兜底页是静态路由，业务 children 由菜单接口动态补充。 */
export const routes: RouteRecordRaw[] = [
  { path: LOGIN_PATH, name: 'login', component: LoginPage, meta: { title: '登录' } },
  {
    path: NOT_FOUND_PATH,
    name: 'not-found',
    component: NotFoundPage,
    meta: { title: '页面不存在' },
  },
  {
    path: '/',
    name: APP_SHELL_ROUTE_NAME,
    component: AppShell,
    meta: { requiresAuth: true, title: '工作台' },
    children: [],
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'catch-all',
    component: NotFoundPage,
    meta: { title: '页面不存在' },
  },
]

/** 守卫只依赖这些字段，便于测试时注入最小认证上下文。 */
export interface RouteAuthContext {
  readonly isAuthenticated: boolean
  readonly menus: MenuItem[]
  initialize: () => Promise<void>
}

export interface DynamicRouteManager {
  readonly ready: boolean
  register: (menus: MenuItem[]) => void
  remove: () => void
  hasPath: (path: string) => boolean
  defaultPath: (menus: MenuItem[]) => string
}

interface MenuRouteCandidate {
  menu: MenuItem
  path: string
  component: Component
}

interface UnresolvedMenuRouteCandidate {
  menu: MenuItem
  path: string
  component: Component | undefined
}

function isSupportedMenuRoute(
  candidate: UnresolvedMenuRouteCandidate,
): candidate is MenuRouteCandidate {
  if (candidate.component) {
    return true
  }
  // 后端新增菜单必须先完成前端组件白名单映射，否则拒绝注册并落到 404。
  console.warn(`[router] ignore unsupported menu route: ${candidate.path}`)
  return false
}

function normalizePath(path: string): string {
  const normalized = path.trim().replace(BACKSLASH_PATTERN, '/')
  if (!normalized || normalized === '/') {
    return '/'
  }
  const withLeadingSlash = normalized.startsWith('/') ? normalized : `/${normalized}`
  return withLeadingSlash.replace(TRAILING_SLASH_PATTERN, '') || '/'
}

function isPublicPath(path: string): boolean {
  return path === LOGIN_PATH || path === NOT_FOUND_PATH
}

function getMenuRouteCandidates(menus: MenuItem[]): MenuRouteCandidate[] {
  return menus
    .filter((menu) => menu.kind === 'menu' && menu.visible && Boolean(menu.route))
    .map((menu) => {
      const path = normalizePath(menu.route ?? '')
      return { menu, path, component: routeComponents[path] }
    })
    .filter(isSupportedMenuRoute)
}

/** 创建动态路由管理器；每个 Router 实例独立维护自己的注册状态。 */
export function createDynamicRouteManager(router: Router): DynamicRouteManager {
  const routeNames = new Set<string>()
  const routePaths = new Set<string>()
  let ready = false

  function remove(): void {
    // removeRoute 会连同对应的 AppShell 子路由一起移除，防止切换账号后残留访问权限。
    for (const routeName of routeNames) {
      if (router.hasRoute(routeName)) {
        router.removeRoute(routeName)
      }
    }
    routeNames.clear()
    routePaths.clear()
    ready = false
  }

  function register(menus: MenuItem[]): void {
    remove()
    for (const { menu, path, component } of getMenuRouteCandidates(menus)) {
      const routeName = `dynamic:${menu.id}`
      router.addRoute(APP_SHELL_ROUTE_NAME, {
        path: path.slice(1),
        name: routeName,
        component,
        meta: {
          title: menu.name,
          icon: menu.icon,
          permissionCode: menu.permission_code,
          menuId: menu.id,
          dynamic: true,
          requiresAuth: true,
        },
      })
      routeNames.add(routeName)
      routePaths.add(path)
    }
    ready = true
  }

  function hasPath(path: string): boolean {
    return routePaths.has(normalizePath(path))
  }

  function defaultPath(menus: MenuItem[]): string {
    const candidates = getMenuRouteCandidates(menus)
    const dashboard = candidates.find((candidate) => candidate.path === '/dashboard')
    if (dashboard) {
      return dashboard.path
    }
    return candidates[0]?.path ?? NOT_FOUND_PATH
  }

  return {
    get ready() {
      return ready
    },
    register,
    remove,
    hasPath,
    defaultPath,
  }
}

/** 安装全局认证守卫，统一处理 session 恢复、动态路由刷新和无权限访问。 */
export function installRouteGuard(
  router: Router,
  manager: DynamicRouteManager,
  getAuth = useAuthStore,
): void {
  router.beforeEach(async (to) => {
    const auth = getAuth() as unknown as RouteAuthContext
    await auth.initialize()

    if (!auth.isAuthenticated) {
      manager.remove()
      if (isPublicPath(to.path)) {
        return true
      }
      const loginTarget: RouteLocationRaw = {
        path: LOGIN_PATH,
        query: { redirect: to.fullPath },
      }
      return loginTarget
    }

    if (!manager.ready) {
      manager.register(auth.menus)
      // 初次刷新时目标可能先被兜底路由接住，注册完成后重导航一次让 Router 重新匹配。
      if (to.path !== LOGIN_PATH && to.path !== NOT_FOUND_PATH && manager.hasPath(to.path)) {
        return { path: to.fullPath, replace: true }
      }
    }

    if (to.path === LOGIN_PATH || to.path === '/') {
      return manager.defaultPath(auth.menus)
    }
    if (isPublicPath(to.path)) {
      return true
    }
    if (!manager.hasPath(to.path)) {
      return NOT_FOUND_PATH
    }
    return true
  })
}

/** 创建应用 Router；生产使用浏览器历史，测试可注入内存历史。 */
export function createAppRouter(history: RouterHistory = createWebHistory()): Router {
  const router = createRouter({ history, routes })
  installRouteGuard(router, createDynamicRouteManager(router))
  return router
}

const router = createAppRouter()

export default router
