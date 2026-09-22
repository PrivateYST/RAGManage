import type { DashboardHealthState } from './type'
/**
 * 工作台页逻辑：并行读取当前空间的知识库、任务和基础服务状态，
 * 页面只消费整理后的派生数据，避免把请求副作用和展示模板耦合在一起。
 */
import type { KnowledgeBaseRow } from '@/api/admin'
import type { TaskRow } from '@/api/documents'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '@/api/admin'
import { fetchTasks } from '@/api/documents'
import { fetchHealth } from '@/api/health'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

/**
 * 返回工作台所需的响应式状态和派生值。
 * 当前空间为空时会停止请求并清空页面数据，避免展示上一个空间的内容。
 */
export function useDashboardPage() {
  const auth = useAuthStore()
  const toast = useAppToast()
  const currentSpace = computed(() => auth.activeSpace)
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const tasks = ref<TaskRow[]>([])
  const loading = shallowRef(true)
  const serviceReady = shallowRef<DashboardHealthState>(null)

  const currentKnowledgeBase = computed(() => knowledgeBases.value[0])
  const documentCount = computed(() =>
    knowledgeBases.value.reduce((total, item) => total + item.document_count, 0),
  )
  const activeTasks = computed(() =>
    tasks.value.filter((task) => ['queued', 'running'].includes(task.state)),
  )
  const pendingTaskCount = computed(() => activeTasks.value.length)

  /** 载入当前空间的工作台摘要；请求失败统一通过全局 Toast 告知用户。 */
  async function loadDashboard(): Promise<void> {
    if (!currentSpace.value) {
      knowledgeBases.value = []
      tasks.value = []
      serviceReady.value = null
      loading.value = false
      return
    }
    loading.value = true
    const controller = new AbortController()
    try {
      const [knowledgeBaseResponse, taskResponse, health] = await Promise.all([
        fetchKnowledgeBases(currentSpace.value.id),
        fetchTasks({ tenantId: currentSpace.value.id }),
        fetchHealth(controller.signal),
      ])
      knowledgeBases.value = knowledgeBaseResponse.items
      tasks.value = taskResponse.items
      serviceReady.value = health.status === 'ready'
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '工作台数据加载失败')
    } finally {
      controller.abort()
      loading.value = false
    }
  }

  watch(() => auth.activeSpaceId, loadDashboard, { immediate: true })

  return {
    currentSpace,
    knowledgeBases,
    currentKnowledgeBase,
    documentCount,
    activeTasks,
    pendingTaskCount,
    loading,
    serviceReady,
  }
}
