import type { TaskRow } from '@/api/documents'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// @vitest-environment happy-dom
/** 任务中心逻辑回归：保护空间范围、筛选查询、任务变更刷新和失败反馈。 */
import { effectScope, reactive } from 'vue'
import { useTasksPage } from './index'

const api = vi.hoisted(() => ({
  auth: { activeSpaceId: '' },
  fetchKnowledgeBases: vi.fn(),
  fetchTasks: vi.fn(),
  retryTask: vi.fn(),
  cancelTask: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}))

vi.mock('@/api/admin', () => ({ fetchKnowledgeBases: api.fetchKnowledgeBases }))
vi.mock('@/api/documents', () => ({
  cancelTask: api.cancelTask,
  fetchTasks: api.fetchTasks,
  retryTask: api.retryTask,
}))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ error: api.toastError, success: api.toastSuccess }),
}))
vi.mock('@/store/auth', () => ({ useAuthStore: () => api.auth }))

/** 构造完整任务记录以验证过滤和变更后列表刷新。 */
function task(id: string, state: TaskRow['state'], knowledgeBaseId = 'kb-1'): TaskRow {
  return {
    id,
    tenant_id: 'space-1',
    knowledge_base_id: knowledgeBaseId,
    task_type: 'document_parse',
    state,
    attempt: 1,
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    item_count: 2,
    completed_items: 1,
  }
}

/** 将页面 composable 放进 effect scope，使筛选监听可在单测结束时清理。 */
function createPage() {
  const scope = effectScope()
  const page = scope.run(() => useTasksPage())
  if (!page) throw new Error('任务页面 effect scope 未能启动')
  return { page, dispose: () => scope.stop() }
}

describe('tasks page logic', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.auth = reactive({ activeSpaceId: 'space-1' })
    api.fetchKnowledgeBases.mockResolvedValue({ items: [] })
    api.fetchTasks.mockResolvedValue({ items: [] })
    api.retryTask.mockResolvedValue(undefined)
    api.cancelTask.mockResolvedValue(undefined)
  })

  it('loads only the active space and reloads tasks when the knowledge-base filter changes', async () => {
    api.fetchKnowledgeBases.mockResolvedValue({ items: [] })
    api.fetchTasks.mockResolvedValue({ items: [task('task-1', 'queued')] })
    const { page, dispose } = createPage()

    await flushPromises()
    expect(api.fetchKnowledgeBases).toHaveBeenCalledWith('space-1')
    expect(api.fetchTasks).toHaveBeenNthCalledWith(1, { tenantId: 'space-1' })

    page.knowledgeBaseId.value = 'kb-1'
    await flushPromises()
    expect(api.fetchTasks).toHaveBeenNthCalledWith(2, {
      tenantId: 'space-1',
      knowledgeBaseId: 'kb-1',
    })

    page.stateFilter.value = 'queued'
    expect(page.visibleTasks.value.map(({ id }) => id)).toEqual(['task-1'])
    dispose()
  })

  it('reports load failures and clears stale rows when no space is selected', async () => {
    api.fetchTasks.mockRejectedValueOnce(new Error('任务接口不可用'))
    const failed = createPage()

    await flushPromises()
    expect(failed.page.errorMessage.value).toBe('任务接口不可用')
    expect(api.toastError).toHaveBeenCalledWith('任务接口不可用')
    failed.dispose()

    api.auth = reactive({ activeSpaceId: '' })
    const emptySpace = createPage()
    await flushPromises()
    expect(emptySpace.page.knowledgeBases.value).toEqual([])
    expect(emptySpace.page.visibleTasks.value).toEqual([])
    emptySpace.dispose()
  })

  it('retries failed tasks and cancels running tasks before refreshing the list', async () => {
    const failed = task('task-failed', 'failed')
    const running = task('task-running', 'running')
    api.fetchTasks.mockResolvedValue({ items: [failed, running] })
    const { page, dispose } = createPage()
    await flushPromises()

    await page.handleRetry(failed)
    await page.handleCancel(running)

    expect(api.retryTask).toHaveBeenCalledWith('task-failed')
    expect(api.cancelTask).toHaveBeenCalledWith('task-running')
    expect(api.toastSuccess).toHaveBeenNthCalledWith(1, '任务已重新排队')
    expect(api.toastSuccess).toHaveBeenNthCalledWith(2, '任务已取消')
    expect(api.fetchTasks).toHaveBeenCalledTimes(3)
    dispose()
  })
})
