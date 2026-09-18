import type { AuthContext, MenuItem } from '../api/auth'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { currentUser, login, logout } from '../api/auth'

export const useAuthStore = defineStore('auth', () => {
  const context = ref<AuthContext | null>(null)
  const loading = ref(false)
  const initialized = ref(false)
  const error = ref('')

  const isAuthenticated = computed(() => context.value !== null)
  const user = computed(() => context.value?.user ?? null)
  const spaces = computed(() => context.value?.spaces ?? [])
  const menus = computed(() => context.value?.menus ?? [])

  async function initialize(): Promise<void> {
    if (initialized.value)
      return
    loading.value = true
    try {
      context.value = await currentUser()
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
  }

  function can(permission: string): boolean {
    return menus.value.some((menu: MenuItem) => menu.permission_code === permission)
  }

  return { context, loading, initialized, error, isAuthenticated, user, spaces, menus, initialize, signIn, signOut, can }
})
