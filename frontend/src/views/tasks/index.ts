import type { TaskFilterValue } from './type'
/**
 * 任务中心业务逻辑：读取当前空间任务、处理筛选，并封装重试和取消操作。
 * 所有变更操作完成后重新查询列表，确保进度和状态以服务端结果为准。
 */
import type { KnowledgeBaseRow } from '@/api/admin'
import type { TaskRow } from '@/api/documents'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '@/api/admin'
import { cancelTask, fetchTasks, retryTask } from '@/api/documents'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

/** 返回任务中心所需的状态、派生值和异步操作。 */
export function useTasksPage() {
  const auth = useAuthStore()
  const toast = useAppToast()
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const tasks = ref<TaskRow[]>([])
  const knowledgeBaseId = shallowRef<TaskFilterValue>('all')
  const stateFilter = shallowRef<TaskFilterValue>('all')
  const loading = shallowRef(true)
  const busyTaskId = shallowRef<string | null>(null)

  const visibleTasks = computed(() =>
    tasks.value.filter((task) => {
      const matchesKnowledgeBase =
        knowledgeBaseId.value === 'all' || task.knowledge_base_id === knowledgeBaseId.value
      const matchesState = stateFilter.value === 'all' || task.state === stateFilter.value
      return matchesKnowledgeBase && matchesState
    }),
  )
  const knowledgeBaseNames = computed(
    () => new Map(knowledgeBases.value.map((item) => [item.id, item.name])),
  )

  const stateLabels: Record<string, string> = {
    queued: '排队中',
    running: '处理中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    interrupted: '已中断',
  }

  function stateLabel(value: string): string {
    return stateLabels[value] ?? value
  }

  function taskLabel(value: string): string {
    return (
      { document_parse: '文档解析', document_embed: '文档嵌入', index_build: '索引构建' }[value] ??
      value
    )
  }

  function formatDate(value: string): string {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  }

  function progress(task: TaskRow): string {
    if (!task.item_count) return task.state === 'completed' ? '已完成' : '—'
    return `${task.completed_items} / ${task.item_count}`
  }

  /** 首次进入页面或切换空间时同时刷新知识库选项和任务列表。 */
  async function loadData(): Promise<void> {
    loading.value = true
    try {
      if (!auth.activeSpaceId) {
        knowledgeBases.value = []
        tasks.value = []
        return
      }
      const [kbResponse, taskResponse] = await Promise.all([
        fetchKnowledgeBases(auth.activeSpaceId),
        fetchTasks({ tenantId: auth.activeSpaceId }),
      ])
      knowledgeBases.value = kbResponse.items
      tasks.value = taskResponse.items
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '任务加载失败')
    } finally {
      loading.value = false
    }
  }

  async function refreshTasksForKnowledgeBase(value: TaskFilterValue): Promise<void> {
    if (!auth.activeSpaceId) return
    loading.value = true
    try {
      tasks.value = (
        await fetchTasks({
          tenantId: auth.activeSpaceId,
          ...(value === 'all' ? {} : { knowledgeBaseId: value }),
        })
      ).items
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '任务加载失败')
    } finally {
      loading.value = false
    }
  }

  async function handleRetry(task: TaskRow): Promise<void> {
    busyTaskId.value = task.id
    try {
      await retryTask(task.id)
      toast.success('任务已重新排队')
      await loadData()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '任务重试失败')
    } finally {
      busyTaskId.value = null
    }
  }

  async function handleCancel(task: TaskRow): Promise<void> {
    busyTaskId.value = task.id
    try {
      await cancelTask(task.id)
      toast.success('任务已取消')
      await loadData()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '任务取消失败')
    } finally {
      busyTaskId.value = null
    }
  }

  watch(
    () => auth.activeSpaceId,
    async () => {
      knowledgeBaseId.value = 'all'
      await loadData()
    },
    { immediate: true },
  )

  watch(knowledgeBaseId, async (value, previousValue) => {
    if (value === previousValue) return
    await refreshTasksForKnowledgeBase(value)
  })

  return {
    knowledgeBases,
    visibleTasks,
    knowledgeBaseNames,
    knowledgeBaseId,
    stateFilter,
    loading,
    busyTaskId,
    stateLabel,
    taskLabel,
    formatDate,
    progress,
    loadData,
    handleRetry,
    handleCancel,
  }
}
