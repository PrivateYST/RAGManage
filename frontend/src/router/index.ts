/**
 * 应用路由模块：集中维护页面路由、布局层级和登录态导航守卫。
 *
 * main.ts 只负责创建应用并注册插件，页面组件和路由规则在这里统一管理，
 * 这样新增页面时不会把启动入口变成路由配置与业务初始化的混合文件。
 */
import type { RouteRecordRaw } from 'vue-router'
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
import SearchTestPage from '@/views/search-test/index.vue'
import TasksPage from '@/views/tasks/index.vue'

/** 路由表：登录页独立于需要认证的工作台布局，其余页面挂在 AppShell 下。 */
export const routes: RouteRecordRaw[] = [
  { path: '/login', component: LoginPage, meta: { title: '登录' } },
  {
    path: '/',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', component: DashboardPage, meta: { title: '工作台' } },
      { path: 'knowledge-bases', component: ManagementPage, meta: { title: '知识库' } },
      { path: 'documents', component: DocumentsPage, meta: { title: '文档管理' } },
      { path: 'releases', component: BuildsPage, meta: { title: '构建与发布' } },
      { path: 'chat', component: ChatPage, meta: { title: '知识问答' } },
      { path: 'search-test', component: SearchTestPage, meta: { title: '检索调试' } },
      { path: 'tasks', component: TasksPage, meta: { title: '任务中心' } },
      { path: 'members', component: MembersPage, meta: { title: '成员与权限' } },
      { path: 'system/spaces', component: ManagementPage, meta: { title: '空间管理' } },
      { path: 'system/users', component: ManagementPage, meta: { title: '用户管理' } },
      { path: 'system/roles', component: ManagementPage, meta: { title: '角色管理' } },
      { path: 'system/menus', component: ManagementPage, meta: { title: '菜单管理' } },
      { path: 'system/audit', component: AuditPage, meta: { title: '操作日志' } },
      { path: 'system/models', component: ModelsPage, meta: { title: '模型服务' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/**
 * 全局登录态守卫：首次进入应用时恢复 session，再决定是否允许访问工作台。
 * 未登录访问受保护路由统一回到登录页；已登录用户访问登录页则回到工作台。
 */
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.initialize()
  if (to.meta.requiresAuth && !auth.isAuthenticated)
    return '/login'
  if (to.path === '/login' && auth.isAuthenticated)
    return '/dashboard'
  return true
})

export default router
