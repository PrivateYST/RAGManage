import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import AppShell from './layouts/AppShell.vue'
import DashboardPage from './pages/DashboardPage.vue'
import DocumentsPage from './pages/DocumentsPage.vue'
import LoginPage from './pages/LoginPage.vue'
import ManagementPage from './pages/ManagementPage.vue'
import TasksPage from './pages/TasksPage.vue'
import { useAuthStore } from './stores/auth'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
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
        { path: 'releases', component: ManagementPage, meta: { title: '发布版本' } },
        { path: 'chat', component: ManagementPage, meta: { title: '知识问答' } },
        { path: 'search-test', component: ManagementPage, meta: { title: '检索调试' } },
        { path: 'tasks', component: TasksPage, meta: { title: '任务中心' } },
        { path: 'members', component: ManagementPage, meta: { title: '空间成员' } },
        { path: 'system/spaces', component: ManagementPage, meta: { title: '空间管理' } },
        { path: 'system/users', component: ManagementPage, meta: { title: '用户管理' } },
        { path: 'system/roles', component: ManagementPage, meta: { title: '角色管理' } },
        { path: 'system/menus', component: ManagementPage, meta: { title: '菜单管理' } },
        { path: 'system/audit', component: ManagementPage, meta: { title: '操作日志' } },
        { path: 'system/models', component: ManagementPage, meta: { title: '模型服务' } },
      ],
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.initialize()
  if (to.meta.requiresAuth && !auth.isAuthenticated)
    return '/login'
  if (to.path === '/login' && auth.isAuthenticated)
    return '/dashboard'
  return true
})

createApp(App).use(createPinia()).use(router).mount('#app')
