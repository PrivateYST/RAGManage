/** 角色管理逻辑：读取平台角色并同步非系统角色的菜单权限。 */
import type { MenuRow, RoleRow } from '@/api/admin'
import { ref } from 'vue'
import { fetchMenus, fetchRoles, updateRoleMenus } from '@/api/admin'
import { useAppToast } from '@/composables/useToast'

/** 为角色页提供列表、重试和权限同步状态。 */
export function useRolesPage() {
  const toast = useAppToast()
  const roles = ref<RoleRow[]>([])
  const loading = ref(false)
  const loadError = ref('')
  const syncingRoleId = ref<string | null>(null)

  /** 读取服务端角色；错误状态留在页面供管理员重试。 */
  async function loadRoles(): Promise<void> {
    loading.value = true
    loadError.value = ''
    try {
      roles.value = (await fetchRoles()).items
    } catch (cause) {
      loadError.value = cause instanceof Error ? cause.message : '角色列表加载失败'
      toast.error(loadError.value)
    } finally {
      loading.value = false
    }
  }

  /** 系统角色由平台初始化保护；自定义角色同步当前菜单集并刷新结果。 */
  async function syncRoleMenus(role: RoleRow): Promise<void> {
    if (role.is_system) {
      toast.error('系统角色权限由平台初始化维护，不能直接修改')
      return
    }
    syncingRoleId.value = role.id
    try {
      const menus: MenuRow[] = (await fetchMenus()).items
      await updateRoleMenus(
        role.id,
        menus.map((menu) => menu.id),
      )
      toast.success('角色权限已更新')
      await loadRoles()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '角色权限更新失败')
    } finally {
      syncingRoleId.value = null
    }
  }

  return { roles, loading, loadError, syncingRoleId, loadRoles, syncRoleMenus }
}
