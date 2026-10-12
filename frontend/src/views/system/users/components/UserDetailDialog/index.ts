/** 用户详情数据逻辑：按打开的用户 ID 请求空间授权及脱敏后的审计历史。 */
import type { UserDetailDialogProps } from './type'
import type { UserDetail } from '@/api/admin'
import { ref, watch } from 'vue'
import { fetchUserDetail } from '@/api/admin'
import { useAppToast } from '@/composables/useToast'

/** 切换目标用户时清理旧详情，避免短暂显示其他账号的授权记录。 */
export function useUserDetailDialog(props: UserDetailDialogProps) {
  const toast = useAppToast()
  const detail = ref<UserDetail | null>(null)
  const loading = ref(false)

  /** 弹窗开启且有目标账号时读取详情；请求失败由 Toast 告知，弹窗仍可关闭。 */
  watch(
    () => [props.open, props.user?.id] as const,
    async ([open, userId]) => {
      detail.value = null
      if (!open || !userId) return
      loading.value = true
      try {
        detail.value = await fetchUserDetail(userId)
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : '用户详情加载失败')
      } finally {
        loading.value = false
      }
    },
    { immediate: true },
  )

  return { detail, loading }
}
