/** 操作日志页面状态组合器，统一管理授权范围、筛选、游标分页和详情选择。 */

import type { AuditLogItem } from '../../api/audit'
import type { AuditFilterState, SelectedAuditLog } from './type'
import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { fetchAuditLogs } from '../../api/audit'
import { useAuthStore } from '../../stores/auth'

export function useAuditLogs() {
  /** 页面数据只从服务端审计接口读取，空间上下文由全局认证 Store 提供。 */
  const auth = useAuthStore()
  const items = ref<AuditLogItem[]>([])
  const filters = reactive<AuditFilterState>({
    scope: auth.activeSpaceId ? 'space' : 'platform',
    actionPrefix: '',
    actor: '',
    targetType: '',
  })
  const loading = shallowRef(false)
  const loadingMore = shallowRef(false)
  const error = shallowRef('')
  const nextCursor = shallowRef<string | null>(null)
  const selected = shallowRef<SelectedAuditLog>(null)
  const isPlatformAdmin = computed(() => auth.user?.platform_role === 'platform_admin')
  const canLoadSpace = computed(() => filters.scope !== 'space' || Boolean(auth.activeSpaceId))

  /** 按当前范围加载首屏或下一页；首屏查询会替换旧结果并重置游标。 */
  async function load(reset = true): Promise<void> {
    if (!canLoadSpace.value)
      return
    if (reset) {
      loading.value = true
      nextCursor.value = null
    }
    else {
      loadingMore.value = true
    }
    error.value = ''
    try {
      const page = await fetchAuditLogs({
        ...(filters.scope === 'space' ? { tenantId: auth.activeSpaceId } : {}),
        actionPrefix: filters.actionPrefix,
        actor: filters.actor.trim(),
        targetType: filters.targetType,
        ...(reset ? {} : { cursor: nextCursor.value ?? undefined }),
        limit: 30,
      })
      items.value = reset ? page.items : [...items.value, ...page.items]
      nextCursor.value = page.next_cursor
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '操作日志加载失败'
      if (reset)
        items.value = []
    }
    finally {
      loading.value = false
      loadingMore.value = false
    }
  }

  /** 清空组合筛选条件并重新查询当前范围。 */
  function resetFilters(): void {
    filters.actionPrefix = ''
    filters.actor = ''
    filters.targetType = ''
    void load(true)
  }

  /** 空间或范围变化会使旧结果失效，因此立即重新查询。 */
  watch(
    [() => auth.activeSpaceId, () => filters.scope],
    () => void load(true),
    { immediate: true },
  )

  return {
    auth,
    items,
    filters,
    loading,
    loadingMore,
    error,
    nextCursor,
    selected,
    isPlatformAdmin,
    load,
    resetFilters,
  }
}
