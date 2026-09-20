<script setup lang="ts">
import type { LucideIcon } from 'lucide-vue-next'
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Cpu,
  Files,
  GitBranch,
  KeyRound,
  LayoutDashboard,
  Library,
  ListTodo,
  LogOut,
  Menu,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  ScrollText,
  Search,
  SearchCheck,
  Settings2,
  ShieldCheck,
  UserRound,
  Users,
  X,
} from 'lucide-vue-next'
import { computed, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { changePassword } from '../api/auth'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const collapsed = shallowRef(false)
const profileOpen = shallowRef(false)
const passwordOpen = shallowRef(false)
const passwordBusy = shallowRef(false)
const passwordError = shallowRef('')
const passwordSuccess = shallowRef('')
const currentPassword = shallowRef('')
const newPassword = shallowRef('')
const confirmPassword = shallowRef('')
const openGroups = shallowRef(new Set(['knowledge', 'retrieval', 'customers', 'system']))

const iconMap: Record<string, LucideIcon> = {
  LayoutDashboard,
  Library,
  Files,
  GitBranch,
  MessageSquare,
  SearchCheck,
  Search,
  ListTodo,
  Building2,
  Users,
  Settings2,
  UserRound,
  ShieldCheck,
  Menu,
  ScrollText,
  Cpu,
}

const topLevelMenus = computed(() => auth.menus.filter(item =>
  (item.kind === 'menu' || item.kind === 'directory') && item.parent_id === null,
))
const childMenus = (parentId: string) => auth.menus.filter(item => item.parent_id === parentId)
const isActive = (path: string | null) => path === route.path || (path !== '/' && path && route.path.startsWith(`${path}/`))
const isOpen = (code: string) => openGroups.value.has(code)
const userInitial = computed(() => auth.user?.display_name?.slice(0, 1) || 'U')
const userRoleLabel = computed(() => auth.user?.platform_role === 'platform_admin' ? '平台管理员' : '空间成员')
const activeSpaceId = computed({
  get: () => auth.activeSpaceId,
  set: (spaceId: string) => auth.setActiveSpace(spaceId),
})

function toggle(code: string): void {
  if (collapsed.value)
    collapsed.value = false
  const next = new Set(openGroups.value)
  if (next.has(code))
    next.delete(code)
  else next.add(code)
  openGroups.value = next
}

function openProfileMenu(): void {
  profileOpen.value = true
}

function closeProfileMenu(): void {
  profileOpen.value = false
}

function openPasswordDialog(): void {
  profileOpen.value = false
  passwordError.value = ''
  passwordSuccess.value = ''
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  passwordOpen.value = true
}

function closePasswordDialog(): void {
  if (!passwordBusy.value)
    passwordOpen.value = false
}

async function submitPasswordChange(): Promise<void> {
  passwordError.value = ''
  passwordSuccess.value = ''
  if (newPassword.value.length < 8) {
    passwordError.value = '新密码至少需要 8 位'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }
  passwordBusy.value = true
  try {
    await changePassword(currentPassword.value, newPassword.value)
    passwordSuccess.value = '密码已修改，请使用新密码重新登录'
    window.setTimeout(async () => {
      await auth.signOut()
      await router.push('/login')
    }, 900)
  }
  catch (cause) {
    passwordError.value = cause instanceof Error ? cause.message : '密码修改失败'
  }
  finally {
    passwordBusy.value = false
  }
}

function handleProfileFocusOut(event: FocusEvent): void {
  const container = event.currentTarget
  const nextTarget = event.relatedTarget
  if (container instanceof HTMLElement && !(nextTarget instanceof Node && container.contains(nextTarget)))
    closeProfileMenu()
}

async function signOut(): Promise<void> {
  profileOpen.value = false
  await auth.signOut()
  await router.push('/login')
}
</script>

<template>
  <div class="admin-shell">
    <aside class="admin-sidebar" :class="{ collapsed }">
      <div class="brand-lockup sidebar-brand">
        <span class="brand-mark">R</span><div v-if="!collapsed" class="brand-copy">
          <strong>RAGManage</strong><small>知识库工作台</small>
        </div>
      </div>
      <div v-if="!collapsed" class="sidebar-workspace">
        <div class="sidebar-label">
          工作空间
        </div>
        <select v-model="activeSpaceId" class="space-select" aria-label="选择客户空间">
          <option v-for="space in auth.spaces" :key="space.id" :value="space.id">
            {{ space.name }}
          </option>
        </select>
      </div>
      <nav class="side-nav nav-scroll" aria-label="主菜单">
        <template v-for="item in topLevelMenus" :key="item.id">
          <RouterLink v-if="item.kind === 'menu'" :to="item.route || '/dashboard'" class="nav-link" :title="collapsed ? item.name : undefined" :class="[{ active: isActive(item.route) }]">
            <component :is="iconMap[item.icon || '']" :size="17" /><span v-if="!collapsed">{{ item.name }}</span>
          </RouterLink>
          <div v-else class="nav-group">
            <button class="nav-group-title" :title="collapsed ? item.name : undefined" @click="toggle(item.code)">
              <component :is="iconMap[item.icon || '']" :size="17" /><span v-if="!collapsed">{{ item.name }}</span><ChevronDown v-if="!collapsed && isOpen(item.code)" :size="15" /><ChevronRight v-else-if="!collapsed" :size="15" />
            </button>
            <div v-if="!collapsed && isOpen(item.code)" class="nav-children">
              <RouterLink v-for="child in childMenus(item.id)" :key="child.id" :to="child.route || '/dashboard'" class="nav-child" :class="[{ active: isActive(child.route) }]">
                {{ child.name }}
              </RouterLink>
            </div>
          </div>
        </template>
      </nav>
      <div class="sidebar-bottom">
        <div class="service-status">
          <i /><span v-if="!collapsed">服务正常</span>
        </div>
        <button class="collapse-button" :title="collapsed ? '展开侧栏' : '收起侧栏'" @click="collapsed = !collapsed">
          <PanelLeftOpen v-if="collapsed" :size="17" /><PanelLeftClose v-else :size="17" /><span v-if="!collapsed">收起侧栏</span>
        </button>
      </div>
    </aside>
    <main class="admin-main">
      <header class="admin-header" @click="closeProfileMenu">
        <div class="breadcrumbs">
          <span>RAGManage</span><ChevronRight :size="14" /><strong>{{ route.meta.title || '工作台' }}</strong>
        </div><div class="header-meta">
          <span class="env-badge">内网试点</span><span class="header-divider" />
          <div
            class="header-profile"
            @mouseenter="openProfileMenu"
            @mouseleave="closeProfileMenu"
            @focusin="openProfileMenu"
            @focusout="handleProfileFocusOut"
            @keydown.esc="closeProfileMenu"
            @click.stop
          >
            <button class="header-profile-trigger" :aria-expanded="profileOpen" aria-haspopup="menu" @click="openProfileMenu">
              <span class="user-avatar">{{ userInitial }}</span>
              <span class="header-user"><strong>{{ auth.user?.display_name || '用户' }}</strong><small>{{ userRoleLabel }}</small></span>
              <ChevronDown :size="15" :class="{ 'profile-chevron-open': profileOpen }" />
            </button>
            <div v-if="profileOpen" class="profile-menu" role="menu">
              <button class="profile-menu-item" role="menuitem" @click="openPasswordDialog">
                <KeyRound :size="15" />修改密码
              </button>
              <button class="profile-menu-item" role="menuitem" @click="signOut">
                <LogOut :size="15" />退出登录
              </button>
            </div>
          </div>
        </div>
      </header><div class="admin-content">
        <RouterView />
      </div>
    </main>
  </div>
  <div v-if="passwordOpen" class="dialog-backdrop" @click.self="closePasswordDialog">
    <section class="dialog-card password-dialog" aria-labelledby="password-dialog-title">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">
            账号安全
          </p><h2 id="password-dialog-title">
            修改密码
          </h2>
        </div>
        <button class="dialog-close" type="button" aria-label="关闭修改密码" @click="closePasswordDialog">
          <X :size="16" />
        </button>
      </div>
      <form @submit.prevent="submitPasswordChange">
        <label>当前密码<input v-model="currentPassword" type="password" autocomplete="current-password" required></label>
        <label>新密码<input v-model="newPassword" type="password" autocomplete="new-password" minlength="8" required></label>
        <label>确认新密码<input v-model="confirmPassword" type="password" autocomplete="new-password" minlength="8" required></label>
        <p v-if="passwordError" class="field-error">
          {{ passwordError }}
        </p>
        <p v-if="passwordSuccess" class="field-success">
          {{ passwordSuccess }}
        </p>
        <div class="dialog-actions">
          <button class="secondary-button" type="button" :disabled="passwordBusy" @click="closePasswordDialog">
            取消
          </button><button class="primary-button" type="submit" :disabled="passwordBusy">
            {{ passwordBusy ? '提交中…' : '确认修改' }}
          </button>
        </div>
      </form>
    </section>
  </div>
</template>
