/** 用户管理页面逻辑：加载平台用户、协调详情和停用操作，并保留失败反馈。 */
import type { UserRow } from '@/api/admin'
import { ref, shallowRef } from 'vue'
import { fetchUsers, updateUser } from '@/api/admin'
import { useAppToast } from '@/composables/useToast'

/** 为用户管理页面提供列表状态及具备结果反馈的异步操作。 */
export function useUserManagementPage() {
  const toast = useAppToast()
  const users = ref<UserRow[]>([])
  const loading = ref(false)
  const loadError = ref('')
  const selectedUser = shallowRef<UserRow | null>(null)
  const detailOpen = ref(false)
  const pendingStatus = shallowRef<UserRow | null>(null)
  const updatingStatus = ref(false)

  /** 加载服务端用户数据；失败时保留错误提示与显式重试入口。 */
  async function loadUsers(): Promise<void> {
    loading.value = true
    loadError.value = ''
    try {
      users.value = (await fetchUsers()).items
    } catch (cause) {
      loadError.value = cause instanceof Error ? cause.message : '用户数据加载失败'
      toast.error(loadError.value)
    } finally {
      loading.value = false
    }
  }

  /** 打开指定账号详情；子弹窗负责按需读取详情内容。 */
  function openDetails(user: UserRow): void {
    selectedUser.value = user
    detailOpen.value = true
  }

  /** 停用需要先确认；重新启用可直接执行状态更新。 */
  async function toggleStatus(user: UserRow): Promise<void> {
    if (user.status === 'active') {
      pendingStatus.value = user
      return
    }
    await updateStatus(user)
  }

  /** 持久化启停状态并刷新服务端列表，失败时保留当前记录。 */
  async function updateStatus(user: UserRow): Promise<boolean> {
    try {
      const nextStatus = user.status === 'active' ? 'disabled' : 'active'
      await updateUser(user.id, { status: nextStatus })
      toast.success(nextStatus === 'active' ? '用户已启用' : '用户已停用')
      await loadUsers()
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '用户状态更新失败')
      return false
    }
  }

  /** 取消停用确认时清除待操作对象，不产生服务端请求。 */
  function cancelStatus(): void {
    if (!updatingStatus.value) pendingStatus.value = null
  }

  /** 确认停用后调用状态变更；请求期间锁定确认状态避免重复提交。 */
  async function confirmStatus(): Promise<void> {
    const user = pendingStatus.value
    if (!user) return
    updatingStatus.value = true
    try {
      if (await updateStatus(user)) pendingStatus.value = null
    } finally {
      updatingStatus.value = false
    }
  }

  return {
    users,
    loading,
    loadError,
    selectedUser,
    detailOpen,
    pendingStatus,
    updatingStatus,
    loadUsers,
    openDetails,
    toggleStatus,
    cancelStatus,
    confirmStatus,
  }
}
