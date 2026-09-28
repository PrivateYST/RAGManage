/** 会话管理状态与异步业务编排；请求序号避免关闭后迟到响应覆盖下一次打开状态。 */
import type { SessionManagementDialogEmits, SessionManagementDialogProps } from './type'
import type { AuthSession } from '@/api/auth'
import { shallowRef, watch } from 'vue'
import { listSessions, revokeSession } from '@/api/auth'
import { useAppToast } from '@/composables/useToast'

/** 绑定弹窗受控输入和事件，并提供加载、重试、撤销确认的单一状态来源。 */
export function useSessionManagementDialog(
  props: SessionManagementDialogProps,
  emit: SessionManagementDialogEmits,
) {
  const toast = useAppToast()
  const items = shallowRef<AuthSession[]>([])
  const loading = shallowRef(false)
  const loadError = shallowRef('')
  const busyId = shallowRef('')
  const pendingRevoke = shallowRef<AuthSession | null>(null)
  let loadSequence = 0

  /** 刷新服务端列表并忽略较早请求的迟到响应。 */
  async function load(): Promise<void> {
    const sequence = ++loadSequence
    loading.value = true
    loadError.value = ''
    try {
      const result = await listSessions()
      if (sequence === loadSequence) items.value = result.items
    } catch (cause) {
      if (sequence === loadSequence)
        loadError.value = cause instanceof Error ? cause.message : '会话加载失败'
    } finally {
      if (sequence === loadSequence) loading.value = false
    }
  }

  /** 进入撤销确认态；破坏性请求不得由列表行的第一次点击直接触发。 */
  function requestRevoke(session: AuthSession): void {
    pendingRevoke.value = session
  }

  /** 用户取消时清理确认对象，不触发服务端变更。 */
  function cancelRevoke(): void {
    if (!busyId.value) pendingRevoke.value = null
  }

  /** 撤销服务端会话并更新 UI；当前会话撤销后通知外壳清理本地身份并跳转登录。 */
  async function confirmRevoke(): Promise<void> {
    const session = pendingRevoke.value
    if (!session) return
    busyId.value = session.id
    try {
      await revokeSession(session.id)
      pendingRevoke.value = null
      toast.success('登录会话已下线')
      if (session.is_current) {
        emit('close')
        emit('current-session-revoked')
      } else {
        items.value = items.value.filter((item) => item.id !== session.id)
      }
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '会话下线失败')
    } finally {
      busyId.value = ''
    }
  }

  /** 每次打开弹窗都从服务端刷新，避免把上一次打开时的会话状态当作最新值。 */
  watch(
    () => props.open,
    (open) => {
      if (open) void load()
      else {
        loadSequence += 1
        loading.value = false
        pendingRevoke.value = null
      }
    },
    { immediate: true },
  )

  return {
    items,
    loading,
    loadError,
    busyId,
    pendingRevoke,
    load,
    requestRevoke,
    cancelRevoke,
    confirmRevoke,
  }
}
