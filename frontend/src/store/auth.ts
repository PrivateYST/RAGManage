import type { AuthContext, MenuItem } from '@/api/auth'
import { defineStore } from 'pinia'
import { computed, ref, shallowRef } from 'vue'
import { currentUser, login, logout } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const activeSpaceId = shallowRef(localStorage.getItem('ragmanage_active_space_id') ?? '')
  const context = ref<AuthContext | null>(null)
  const loading = ref(false)
  const initialized = ref(false)
  const error = ref('')

  const isAuthenticated = computed(() => context.value !== null)
  const user = computed(() => context.value?.user ?? null)
  const spaces = computed(() => context.value?.spaces ?? [])
  const activeSpace = computed(
    () => spaces.value.find(space => space.id === activeSpaceId.value) ?? null,
  )
  const menus = computed(() => context.value?.menus ?? [])

  function reconcileActiveSpace(): void {
    const available = spaces.value
    if (!available.some(space => space.id === activeSpaceId.value))
      activeSpaceId.value = available[0]?.id ?? ''
    if (activeSpaceId.value)
      localStorage.setItem('ragmanage_active_space_id', activeSpaceId.value)
    else localStorage.removeItem('ragmanage_active_space_id')
  }

  function setActiveSpace(spaceId: string): void {
    if (!spaces.value.some(space => space.id === spaceId))
      return
    activeSpaceId.value = spaceId
    localStorage.setItem('ragmanage_active_space_id', spaceId)
  }

  async function refreshContext(): Promise<void> {
    context.value = await currentUser()
    reconcileActiveSpace()
  }

  async function initialize(): Promise<void> {
    if (initialized.value)
      return
    loading.value = true
    try {
      await refreshContext()
    }
    catch {
      context.value = null
    }
    finally {
      initialized.value = true
      loading.value = false
    }
  }

  async function signIn(loginName: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = ''
    try {
      context.value = await login(loginName, password)
      reconcileActiveSpace()
      initialized.value = true
      return true
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '登录失败，请稍后重试'
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function signOut(): Promise<void> {
    await logout().catch(() => undefined)
    context.value = null
    // 清除初始化标记，下一次进入应用时重新校验浏览器中的 session。
    initialized.value = false
    activeSpaceId.value = ''
    localStorage.removeItem('ragmanage_active_space_id')
  }

  function can(permission: string): boolean {
    return menus.value.some((menu: MenuItem) => menu.permission_code === permission)
  }

  return {
    context,
    loading,
    initialized,
    error,
    isAuthenticated,
    user,
    spaces,
    activeSpaceId,
    activeSpace,
    menus,
    initialize,
    refreshContext,
    signIn,
    signOut,
    setActiveSpace,
    can,
  }
})
