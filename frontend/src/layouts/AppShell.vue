<!--
  应用工作台壳层：承载权限菜单、空间切换、用户操作和路由内容区域。
  桌面端支持固定侧栏折叠，窄屏端将同一份菜单切换为可关闭的抽屉，避免维护两套导航状态。
-->
<script setup lang="ts">
import type { Component } from 'vue'
import { computed, shallowRef, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { changePassword } from '@/api/auth'
import {
  AppDialog,
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
} from '@/components'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useAppToast()
const collapsed = shallowRef(false)
const mobileSidebarOpen = shallowRef(false)
const profileOpen = shallowRef(false)
const passwordOpen = shallowRef(false)
const passwordBusy = shallowRef(false)
const passwordError = shallowRef('')
const currentPassword = shallowRef('')
const newPassword = shallowRef('')
const confirmPassword = shallowRef('')
const openGroups = shallowRef(new Set(['knowledge', 'retrieval', 'customers', 'system']))

const iconMap: Record<string, Component> = {
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

const topLevelMenus = computed(() =>
  auth.menus.filter(
    (item) => (item.kind === 'menu' || item.kind === 'directory') && item.parent_id === null,
  ),
)
/** 目录下只展示可导航菜单；按钮权限供页面操作鉴权使用，不能伪装成页面链接。 */
function childMenus(parentId: string) {
  return auth.menus.filter((item) => item.parent_id === parentId && item.kind === 'menu')
}
function isActive(path: string | null) {
  return path === route.path || (path !== '/' && path && route.path.startsWith(`${path}/`))
}
const isOpen = (code: string) => openGroups.value.has(code)
const userInitial = computed(() => auth.user?.display_name?.slice(0, 1) || 'U')
const userRoleLabel = computed(() =>
  auth.user?.platform_role === 'platform_admin' ? '平台管理员' : '空间成员',
)
const activeSpaceId = computed({
  get: () => auth.activeSpaceId,
  set: (spaceId: string) => auth.setActiveSpace(spaceId),
})

/** 路由切换后收起移动端抽屉，避免用户进入新页面后仍被遮罩覆盖。 */
watch(
  () => route.path,
  () => {
    mobileSidebarOpen.value = false
    profileOpen.value = false
  },
)

function toggle(code: string): void {
  if (collapsed.value) collapsed.value = false
  const next = new Set(openGroups.value)
  if (next.has(code)) next.delete(code)
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
  currentPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  passwordOpen.value = true
}

function closePasswordDialog(): void {
  if (!passwordBusy.value) passwordOpen.value = false
}

async function submitPasswordChange(): Promise<void> {
  passwordError.value = ''
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
    toast.success('密码已修改', '请使用新密码重新登录。')
    window.setTimeout(async () => {
      await auth.signOut()
      await router.push('/login')
    }, 900)
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '密码修改失败')
  } finally {
    passwordBusy.value = false
  }
}

function handleProfileFocusOut(event: FocusEvent): void {
  const container = event.currentTarget
  const nextTarget = event.relatedTarget
  if (
    container instanceof HTMLElement &&
    !(nextTarget instanceof Node && container.contains(nextTarget))
  ) {
    closeProfileMenu()
  }
}

async function signOut(): Promise<void> {
  profileOpen.value = false
  await auth.signOut()
  await router.push('/login')
}
</script>

<template>
  <div class="flex h-screen max-h-screen overflow-hidden bg-canvas text-foreground">
    <div
      v-if="mobileSidebarOpen"
      class="fixed inset-0 z-30 bg-foreground/30 lg:hidden"
      aria-hidden="true"
      @click="mobileSidebarOpen = false"
    />
    <aside
      class="fixed inset-y-0 left-0 z-40 flex h-screen w-[248px] -translate-x-full flex-col overflow-hidden border-r border-border bg-card px-[14px] pb-[16px] pt-[22px] transition-[width,transform] duration-200 lg:relative lg:translate-x-0"
      :class="[
        collapsed ? 'lg:w-[68px] lg:basis-[68px]' : 'lg:w-[248px] lg:basis-[248px]',
        mobileSidebarOpen ? 'translate-x-0' : '-translate-x-full',
      ]"
      aria-label="主导航"
    >
      <div
        class="flex items-center gap-[10px] pb-[28px] text-foreground lg:px-[10px]"
        :class="collapsed ? 'lg:justify-center lg:px-0' : ''"
      >
        <span
          class="grid size-[32px] shrink-0 place-items-center rounded-lg bg-foreground text-lg font-bold text-background"
          >R</span
        >
        <div v-if="!collapsed" class="min-w-0 lg:block">
          <strong class="block text-sm font-semibold tracking-[-0.01em]">RAGManage</strong>
          <small class="mt-[2px] block text-[11px] text-muted-foreground">知识库工作台</small>
        </div>
      </div>
      <div v-if="!collapsed" class="mb-[20px]">
        <div
          class="px-[10px] pb-[6px] text-[10px] font-semibold uppercase tracking-[0.08em] text-muted-foreground"
        >
          工作空间
        </div>
        <select
          v-model="activeSpaceId"
          class="h-[36px] w-full rounded-md border border-border bg-[#fafafa] px-[10px] text-xs text-foreground outline-none transition-colors focus:border-ring focus:ring-2 focus:ring-ring/20"
          aria-label="选择客户空间"
        >
          <option v-for="space in auth.spaces" :key="space.id" :value="space.id">
            {{ space.name }}
          </option>
        </select>
      </div>
      <nav
        class="min-h-0 flex-1 space-y-[2px] overflow-x-hidden overflow-y-auto pr-[2px]"
        aria-label="主菜单"
      >
        <template v-for="item in topLevelMenus" :key="item.id">
          <RouterLink
            v-if="item.kind === 'menu'"
            :to="item.route || '/dashboard'"
            class="flex min-h-[36px] w-full items-center gap-[10px] rounded-md px-[10px] text-left text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :title="collapsed ? item.name : undefined"
            :class="[
              isActive(item.route)
                ? 'bg-secondary font-semibold text-foreground hover:bg-secondary hover:text-foreground'
                : '',
              collapsed ? 'lg:justify-center lg:px-0' : '',
            ]"
            @click="mobileSidebarOpen = false"
          >
            <component :is="iconMap[item.icon || '']" :size="17" aria-hidden="true" />
            <span v-if="!collapsed">{{ item.name }}</span>
          </RouterLink>
          <div v-else>
            <button
              class="flex min-h-[36px] w-full items-center gap-[10px] rounded-md border-0 bg-transparent px-[10px] text-left text-[13px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :title="collapsed ? item.name : undefined"
              @click="toggle(item.code)"
            >
              <component :is="iconMap[item.icon || '']" :size="17" aria-hidden="true" />
              <span v-if="!collapsed">{{ item.name }}</span>
              <ChevronDown
                v-if="!collapsed && isOpen(item.code)"
                class="ml-auto text-muted-foreground"
                :size="15"
                aria-hidden="true"
              />
              <ChevronRight
                v-else-if="!collapsed"
                class="ml-auto text-muted-foreground"
                :size="15"
                aria-hidden="true"
              />
            </button>
            <div
              v-if="!collapsed && isOpen(item.code)"
              class="ml-[19px] flex flex-col gap-[2px] border-l border-border pl-[10px]"
            >
              <RouterLink
                v-for="child in childMenus(item.id)"
                :key="child.id"
                :to="child.route || '/dashboard'"
                class="block rounded-md px-[8px] py-[6px] text-xs text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                :class="[
                  isActive(child.route)
                    ? 'bg-secondary font-semibold text-foreground hover:bg-secondary hover:text-foreground'
                    : '',
                ]"
                @click="mobileSidebarOpen = false"
              >
                {{ child.name }}
              </RouterLink>
            </div>
          </div>
        </template>
      </nav>
      <div class="mt-auto shrink-0">
        <div
          class="flex items-center gap-[6px] border-t border-border px-[10px] py-[12px] text-[11px] text-muted-foreground"
        >
          <i class="size-[6px] rounded-full bg-status-up" aria-hidden="true" /><span
            v-if="!collapsed"
            >服务正常</span
          >
        </div>
        <button
          class="flex min-h-[36px] w-full items-center justify-center gap-[8px] rounded-md border-0 bg-transparent px-[10px] text-left text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          :title="collapsed ? '展开侧栏' : '收起侧栏'"
          @click="collapsed = !collapsed"
        >
          <PanelLeftOpen v-if="collapsed" :size="17" aria-hidden="true" />
          <PanelLeftClose v-else :size="17" aria-hidden="true" />
          <span v-if="!collapsed">收起侧栏</span>
        </button>
      </div>
    </aside>
    <main class="flex h-screen min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <header
        class="relative z-20 flex h-[60px] shrink-0 items-center justify-between border-b border-border bg-card px-[16px] sm:px-[24px] lg:px-[34px]"
        @click="closeProfileMenu"
      >
        <div class="flex min-w-0 items-center gap-[8px] text-xs text-muted-foreground">
          <button
            class="-ml-[8px] inline-flex size-[36px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
            type="button"
            aria-label="打开主菜单"
            :aria-expanded="mobileSidebarOpen"
            @click.stop="mobileSidebarOpen = !mobileSidebarOpen"
          >
            <Menu :size="18" aria-hidden="true" />
          </button>
          <span class="hidden sm:inline">RAGManage</span>
          <ChevronRight class="hidden sm:block" :size="14" aria-hidden="true" />
          <strong class="truncate font-semibold text-foreground">{{
            route.meta.title || '工作台'
          }}</strong>
        </div>
        <div class="flex items-center gap-[14px] text-xs text-muted-foreground">
          <span class="rounded bg-status-up-soft px-[8px] py-[4px] text-[11px] text-status-up"
            >内网试点</span
          >
          <span class="hidden h-[17px] w-px bg-border sm:block" />
          <div
            class="relative"
            @mouseenter="openProfileMenu"
            @mouseleave="closeProfileMenu"
            @focusin="openProfileMenu"
            @focusout="handleProfileFocusOut"
            @keydown.esc="closeProfileMenu"
            @click.stop
          >
            <button
              class="flex min-h-[38px] items-center gap-[8px] rounded-md border-0 bg-transparent px-[4px] py-[2px] text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              :aria-expanded="profileOpen"
              aria-haspopup="menu"
              @click="openProfileMenu"
            >
              <span
                class="grid size-[28px] place-items-center rounded-full bg-secondary text-xs font-semibold text-muted-foreground"
                >{{ userInitial }}</span
              >
              <span class="hidden min-w-[72px] flex-col text-left sm:flex"
                ><strong class="text-xs font-medium leading-tight">{{
                  auth.user?.display_name || '用户'
                }}</strong
                ><small class="mt-[2px] text-[10px] leading-tight text-muted-foreground">{{
                  userRoleLabel
                }}</small></span
              >
              <ChevronDown
                :size="15"
                class="transition-transform"
                :class="{ 'rotate-180': profileOpen }"
                aria-hidden="true"
              />
            </button>
            <!-- 顶部内边距作为悬停桥接区，避免移向菜单时经过空隙触发 mouseleave。 -->
            <div v-if="profileOpen" class="absolute right-0 top-full z-20 w-[176px] pt-[4px]">
              <div
                class="rounded-lg border border-border bg-card p-[6px] shadow-[0_1px_2px_rgb(63_45_91_/_4%),0_8px_24px_rgb(79_58_116_/_6%)]"
                role="menu"
              >
                <button
                  class="flex min-h-[33px] w-full items-center gap-[8px] rounded-md border-0 bg-transparent px-[8px] text-left text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  role="menuitem"
                  @click="openPasswordDialog"
                >
                  <KeyRound :size="15" aria-hidden="true" />修改密码
                </button>
                <button
                  class="flex min-h-[33px] w-full items-center gap-[8px] rounded-md border-0 bg-transparent px-[8px] text-left text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  role="menuitem"
                  @click="signOut"
                >
                  <LogOut :size="15" aria-hidden="true" />退出登录
                </button>
              </div>
            </div>
          </div>
        </div>
      </header>
      <div
        class="mx-auto min-h-0 w-full max-w-[1360px] flex-1 overflow-x-hidden overflow-y-auto overscroll-contain p-[16px] sm:p-[24px] lg:p-[34px]"
      >
        <RouterView />
      </div>
    </main>
  </div>
  <AppDialog
    :open="passwordOpen"
    title="修改密码"
    content-class="w-[min(420px,calc(100vw-2rem))]"
    @close="closePasswordDialog"
  >
    <section class="dialog-card w-full max-w-[420px]" aria-labelledby="password-dialog-title">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">账号安全</p>
          <h2 id="password-dialog-title">修改密码</h2>
        </div>
      </div>
      <form class="grid gap-[14px]" @submit.prevent="submitPasswordChange">
        <label class="grid gap-[8px] text-xs font-medium text-foreground"
          >当前密码<input
            v-model="currentPassword"
            class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
            type="password"
            autocomplete="current-password"
            required
        /></label>
        <label class="grid gap-[8px] text-xs font-medium text-foreground"
          >新密码<input
            v-model="newPassword"
            class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
            type="password"
            autocomplete="new-password"
            minlength="8"
            required
        /></label>
        <label class="grid gap-[8px] text-xs font-medium text-foreground"
          >确认新密码<input
            v-model="confirmPassword"
            class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/20"
            type="password"
            autocomplete="new-password"
            minlength="8"
            required
        /></label>
        <p v-if="passwordError" class="field-error mt-0">
          {{ passwordError }}
        </p>
        <div class="mt-[8px] flex justify-end gap-[8px] border-t border-border pt-[16px]">
          <button
            class="secondary-button"
            type="button"
            :disabled="passwordBusy"
            @click="closePasswordDialog"
          >
            取消</button
          ><button class="primary-button" type="submit" :disabled="passwordBusy">
            {{ passwordBusy ? '提交中…' : '确认修改' }}
          </button>
        </div>
      </form>
    </section>
  </AppDialog>
</template>
