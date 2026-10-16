// @vitest-environment happy-dom
/**
 * 知识库迁移回归：防止路由继续指向聚合页，并验证空间隔离、创建转换和错误反馈。
 */
import type { KnowledgeBaseRow } from '@/api/admin'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick, reactive } from 'vue'

import { routeComponents } from '@/router'
import { useKnowledgeBasesPage } from './index'

const api = vi.hoisted(() => ({
  fetchKnowledgeBases: vi.fn(),
  createKnowledgeBase: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
  auth: { activeSpaceId: '12', activeSpace: { name: '医院 A' } },
}))

vi.mock('@/api/admin', () => ({
  fetchKnowledgeBases: api.fetchKnowledgeBases,
  createKnowledgeBase: api.createKnowledgeBase,
}))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: api.success, error: api.error }),
}))
vi.mock('@/store/auth', () => ({ useAuthStore: () => api.auth }))

/** 构造 API 返回值，保持测试与实际知识库行契约一致。 */
function knowledgeBase(): KnowledgeBaseRow {
  return {
    id: '1',
    tenant_id: '12',
    name: '临床指南',
    description: '',
    purpose: 'general',
    status: 'draft',
    active_release_id: null,
    document_count: 0,
    updated_at: '2026-01-01T00:00:00Z',
  }
}

describe('knowledge base management migration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    api.auth = reactive({ activeSpaceId: '12', activeSpace: { name: '医院 A' } })
    api.fetchKnowledgeBases.mockResolvedValue({ items: [knowledgeBase()] })
    api.createKnowledgeBase.mockResolvedValue(knowledgeBase())
  })

  it('maps knowledge bases to a dedicated page component', () => {
    expect(routeComponents['/knowledge-bases']).toBeDefined()
    expect(routeComponents['/knowledge-bases']).not.toBe(routeComponents['/system/spaces'])
  })

  it('loads only the active space and reloads when the active space changes', async () => {
    const page = useKnowledgeBasesPage()
    await vi.waitFor(() => expect(api.fetchKnowledgeBases).toHaveBeenCalledWith('12'))
    expect(page.rows.value).toHaveLength(1)

    api.auth.activeSpaceId = '13'
    await nextTick()
    await vi.waitFor(() => expect(api.fetchKnowledgeBases).toHaveBeenCalledWith('13'))
  })

  it('converts the selected space ID for creation and refreshes the list', async () => {
    const page = useKnowledgeBasesPage()
    await vi.waitFor(() => expect(api.fetchKnowledgeBases).toHaveBeenCalledOnce())
    page.openCreateDialog()
    await page.saveKnowledgeBase({
      tenant_id: '12',
      name: '临床指南',
      description: '诊疗规则',
      purpose: 'rule',
    })

    expect(api.createKnowledgeBase).toHaveBeenCalledWith({
      tenant_id: 12,
      name: '临床指南',
      description: '诊疗规则',
      purpose: 'rule',
      owner_user_id: null,
      valid_from: null,
      valid_until: null,
      business_tags: [],
    })
    expect(api.success).toHaveBeenCalledWith('知识库已创建')
    expect(api.fetchKnowledgeBases).toHaveBeenCalledTimes(2)
    expect(page.dialogOpen.value).toBe(false)
  })

  it('retains a retryable loading error and reports create failures', async () => {
    api.fetchKnowledgeBases.mockRejectedValueOnce(new Error('空间无权访问'))
    const page = useKnowledgeBasesPage()
    await vi.waitFor(() => expect(page.loadError.value).toBe('空间无权访问'))
    expect(api.error).toHaveBeenCalledWith('空间无权访问')

    api.createKnowledgeBase.mockRejectedValueOnce(new Error('名称重复'))
    await page.saveKnowledgeBase({
      tenant_id: '12',
      name: '临床指南',
      description: '',
      purpose: 'general',
    })
    expect(api.error).toHaveBeenCalledWith('名称重复')
    expect(page.dialogOpen.value).toBe(false)
  })
})
