// @vitest-environment happy-dom
/**
 * 文档页迁移回归：保护当前空间/知识库边界、查询参数恢复及文档操作反馈。
 */
import type { KnowledgeBaseRow } from '@/api/admin'
import type { DocumentRow } from '@/api/documents'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { routeComponents } from '@/router'
import { validateUploadFile } from './components/UploadDialog'
import { useDocumentsPage } from './index'

const mocks = vi.hoisted(() => ({
  route: { query: {} as Record<string, unknown>, fullPath: '/documents' },
  auth: { activeSpaceId: '7' },
  fetchKnowledgeBases: vi.fn(),
  fetchDocuments: vi.fn(),
  uploadDocument: vi.fn(),
  deleteDocument: vi.fn(),
  disableDocument: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('vue-router', async (importOriginal) => ({
  ...(await importOriginal<typeof import('vue-router')>()),
  useRoute: () => mocks.route,
}))
vi.mock('@/store/auth', () => ({ useAuthStore: () => mocks.auth }))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: mocks.success, error: mocks.error }),
}))
vi.mock('@/api/admin', () => ({ fetchKnowledgeBases: mocks.fetchKnowledgeBases }))
vi.mock('@/api/documents', () => ({
  compareDocumentVersions: vi.fn(),
  deleteDocument: mocks.deleteDocument,
  disableDocument: mocks.disableDocument,
  documentVersionDownloadUrl: vi.fn(),
  fetchDocument: vi.fn(),
  fetchDocuments: mocks.fetchDocuments,
  fetchVersionPreview: vi.fn(),
  rebuildKnowledgeBase: vi.fn(),
  reparseDocument: vi.fn(),
  uploadDocument: mocks.uploadDocument,
}))

/** 最小知识库数据确保所选项来自本空间 API 响应。 */
function knowledgeBase(id = '10'): KnowledgeBaseRow {
  return {
    id,
    tenant_id: '7',
    name: `知识库 ${id}`,
    description: '',
    purpose: 'general',
    status: 'active',
    active_release_id: null,
    document_count: 1,
    updated_at: '2026-01-01T00:00:00Z',
  }
}

/** 文档列表最小行数据用于验证过滤与确认后刷新。 */
function documentRow(): DocumentRow {
  return {
    id: '21',
    title: '临床指南.pdf',
    status: 'active',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    version_id: 'version-1',
    version_no: 1,
    parse_status: 'complete',
    file_size: 128,
    mime_type: 'application/pdf',
    version_created_at: '2026-01-01T00:00:00Z',
    published: false,
  }
}

describe('documents page migration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    mocks.auth = { activeSpaceId: '7' }
    mocks.route = { query: {}, fullPath: '/documents' }
    mocks.fetchKnowledgeBases.mockResolvedValue({ items: [knowledgeBase()] })
    mocks.fetchDocuments.mockResolvedValue({ items: [documentRow()] })
    mocks.uploadDocument.mockResolvedValue(undefined)
    mocks.deleteDocument.mockResolvedValue(undefined)
    mocks.disableDocument.mockResolvedValue(undefined)
  })

  it('uses a dedicated route component', () => {
    expect(routeComponents['/documents']).toBeDefined()
    expect(routeComponents['/documents']).not.toBe(routeComponents['/knowledge-bases'])
  })

  it('restores only a knowledge base returned for the active space and loads its documents', async () => {
    mocks.route.query = { knowledge_base_id: '10' }
    const page = useDocumentsPage()

    await vi.waitFor(() => expect(mocks.fetchDocuments).toHaveBeenCalledWith('10'))
    expect(mocks.fetchKnowledgeBases).toHaveBeenCalledWith('7')
    expect(page.activeKnowledgeBaseId.value).toBe('10')
    expect(page.visibleDocuments.value).toHaveLength(1)
  })

  it('uploads to the selected knowledge base and reloads its list', async () => {
    const page = useDocumentsPage()
    await vi.waitFor(() => expect(mocks.fetchDocuments).toHaveBeenCalledOnce())
    const file = new File(['content'], 'guide.pdf', { type: 'application/pdf' })

    await page.handleUpload(file)

    expect(mocks.uploadDocument).toHaveBeenCalledWith('10', file)
    expect(mocks.fetchDocuments).toHaveBeenCalledTimes(2)
    expect(mocks.success).toHaveBeenCalledWith(
      '文档上传成功',
      '后台解析完成后即可进入构建和发布流程。',
    )
  })

  it('waits for explicit confirmation before deleting and then refreshes the list', async () => {
    const page = useDocumentsPage()
    await vi.waitFor(() => expect(mocks.fetchDocuments).toHaveBeenCalledOnce())
    page.requestRemove(documentRow())
    expect(mocks.deleteDocument).not.toHaveBeenCalled()

    await page.confirmDocumentAction()

    expect(mocks.deleteDocument).toHaveBeenCalledWith('21')
    expect(mocks.fetchDocuments).toHaveBeenCalledTimes(2)
    expect(mocks.success).toHaveBeenCalledWith('文档已删除', '文档已从列表隐藏，历史记录仍会保留。')
  })

  it('keeps a retryable list error and reports upload failure', async () => {
    mocks.fetchKnowledgeBases.mockRejectedValueOnce(new Error('空间不可用'))
    const page = useDocumentsPage()
    await vi.waitFor(() => expect(page.knowledgeBasesError.value).toBe('空间不可用'))
    expect(mocks.error).toHaveBeenCalledWith('空间不可用')

    page.activeKnowledgeBaseId.value = '10'
    mocks.uploadDocument.mockRejectedValueOnce(new Error('文件格式错误'))
    await page.handleUpload(new File(['x'], 'guide.pdf'))
    expect(page.uploadError.value).toBe('文件格式错误')
  })

  it('validates supported upload extensions, size limit, and empty files', () => {
    expect(validateUploadFile(new File(['ok'], 'guide.pdf'))).toBe('')
    expect(validateUploadFile(new File(['x'], 'guide.exe'))).toContain('仅支持')
    expect(validateUploadFile(new File([], 'empty.txt'))).toBe('不能上传空文件')
    expect(validateUploadFile(new File([new Uint8Array(50 * 1024 * 1024 + 1)], 'large.pdf'))).toBe(
      '文件不能超过 50 MB',
    )
  })
})
