// @vitest-environment happy-dom
/** 工作台迁移回归：验证空间隔离、汇总派生值、并行失败反馈与无空间清理。 */
import type { KnowledgeBaseRow } from '@/api/admin'
import type { TaskRow } from '@/api/documents'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { routeComponents } from '@/router'
import { useDashboardPage } from './index'

const api = vi.hoisted(() => ({
  auth: { activeSpace: null as { id: string; name: string } | null, activeSpaceId: '7' },
  fetchKnowledgeBases: vi.fn(),
  fetchTasks: vi.fn(),
  fetchHealth: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/api/admin', () => ({ fetchKnowledgeBases: api.fetchKnowledgeBases }))
vi.mock('@/api/documents', () => ({ fetchTasks: api.fetchTasks }))
vi.mock('@/api/health', () => ({ fetchHealth: api.fetchHealth }))
vi.mock('@/composables/useToast', () => ({ useAppToast: () => ({ error: api.toastError }) }))
vi.mock('@/store/auth', () => ({ useAuthStore: () => api.auth }))

/** 最小知识库行支持文档数汇总测试。 */
function knowledgeBase(id: string, count: number): KnowledgeBaseRow {
  return {
    id,
    tenant_id: '7',
    name: `KB ${id}`,
    description: '',
    purpose: 'general',
    status: 'draft',
    active_release_id: null,
    document_count: count,
    updated_at: '2026-01-01T00:00:00Z',
  }
}

/** 最小任务行覆盖活动任务计数规则。 */
function task(state: TaskRow['state'], id: string): TaskRow {
  return {
    id,
    tenant_id: '7',
    knowledge_base_id: '10',
    task_type: 'document_parse',
    state,
    attempt: 1,
    item_count: 1,
    completed_items: 0,
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('dashboard migration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    api.auth = { activeSpace: { id: '7', name: '医院 A' }, activeSpaceId: '7' }
    api.fetchKnowledgeBases.mockResolvedValue({
      items: [knowledgeBase('10', 3), knowledgeBase('11', 2)],
    })
    api.fetchTasks.mockResolvedValue({ items: [task('queued', '1'), task('completed', '2')] })
    api.fetchHealth.mockResolvedValue({ status: 'ready' })
  })

  it('remains registered as the dedicated dashboard route', () => {
    expect(routeComponents['/dashboard']).toBeDefined()
    expect(routeComponents['/dashboard']).not.toBe(routeComponents['/knowledge-bases'])
  })

  it('loads summaries for the active space and derives counts', async () => {
    const page = useDashboardPage()

    await vi.waitFor(() => expect(page.loading.value).toBe(false))

    expect(api.fetchKnowledgeBases).toHaveBeenCalledWith('7')
    expect(api.fetchTasks).toHaveBeenCalledWith({ tenantId: '7' })
    expect(page.documentCount.value).toBe(5)
    expect(page.pendingTaskCount.value).toBe(1)
    expect(page.serviceReady.value).toBe(true)
  })

  it('retains an error and clears loading when one parallel request fails', async () => {
    api.fetchTasks.mockRejectedValueOnce(new Error('任务服务不可用'))
    const page = useDashboardPage()

    await vi.waitFor(() => expect(page.loading.value).toBe(false))

    expect(page.errorMessage.value).toBe('任务服务不可用')
    expect(api.toastError).toHaveBeenCalledWith('任务服务不可用')
  })

  it('clears previous-space data when there is no active space', async () => {
    api.auth = { activeSpace: null, activeSpaceId: '' }
    const page = useDashboardPage()

    await vi.waitFor(() => expect(page.loading.value).toBe(false))

    expect(page.knowledgeBases.value).toEqual([])
    expect(page.activeTasks.value).toEqual([])
    expect(api.fetchKnowledgeBases).not.toHaveBeenCalled()
  })
})
