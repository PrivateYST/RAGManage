import type { KnowledgeBasePurposeLabels, PendingDocumentAction } from './type'
import type { KnowledgeBaseRow } from '@/api/admin'
import type { ChunkRow, DocumentDetail, DocumentRow, DocumentVersionDiff } from '@/api/documents'
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { fetchKnowledgeBases } from '@/api/admin'
import {
  compareDocumentVersions,
  deleteDocument,
  disableDocument,
  documentVersionDownloadUrl,
  fetchDocument,
  fetchDocuments,
  fetchVersionPreview,
  rebuildKnowledgeBase,
  reparseDocument,
  uploadDocument,
} from '@/api/documents'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'
/** 文档管理页面逻辑：协调空间内知识库、文档生命周期、上传与详情预览。 */
export function useDocumentsPage() {
  const auth = useAuthStore()
  const route = useRoute()
  const toast = useAppToast()
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const activeKnowledgeBaseId = shallowRef('')
  const documents = ref<DocumentRow[]>([])
  const searchQuery = shallowRef('')
  const statusFilter = shallowRef('all')
  const loading = shallowRef(false)
  const loadingKnowledgeBases = shallowRef(false)
  // 页面级错误与 Toast 并存，保证列表请求失败后仍有可见、可重试的反馈。
  const knowledgeBasesError = shallowRef('')
  const documentsError = shallowRef('')
  const uploadError = shallowRef('')
  const uploadOpen = shallowRef(false)
  const uploading = shallowRef(false)
  const busyDocumentId = shallowRef<string | null>(null)
  const detail = ref<DocumentDetail | null>(null)
  const detailChunks = ref<ChunkRow[]>([])
  const detailLoading = shallowRef(false)
  const detailChunksLoading = shallowRef(false)
  const detailChunksError = shallowRef('')
  const versionDiff = shallowRef<DocumentVersionDiff | null>(null)
  const versionDiffLoading = shallowRef(false)
  const highlightedChunkId = shallowRef('')
  const pendingDocumentAction = shallowRef<PendingDocumentAction | null>(null)
  let openedCitationKey = ''

  const visibleDocuments = computed(() => {
    const query = searchQuery.value.trim().toLocaleLowerCase()
    return documents.value.filter((document) => {
      const matchesQuery = !query || document.title.toLocaleLowerCase().includes(query)
      const matchesStatus =
        statusFilter.value === 'all' || document.parse_status === statusFilter.value
      return matchesQuery && matchesStatus
    })
  })

  const activeKnowledgeBase = computed(() =>
    knowledgeBases.value.find((item) => item.id === activeKnowledgeBaseId.value),
  )

  const purposeLabels: KnowledgeBasePurposeLabels = {
    general: '通用知识',
    product: '产品说明',
    troubleshooting: '故障排查',
    rule: '业务规则',
  }

  /** 将解析器定位字段转成用户可读的页码、表格和区域信息，未知字段原样保留。 */
  function formatLocator(locator: Record<string, number>): string {
    const labels: Record<string, string> = {
      page: '第',
      table: '表格',
      region: '区域',
      row: '行',
      column: '列',
    }
    return Object.entries(locator)
      .map(([key, value]) =>
        key === 'page' ? `${labels.page}${value}页` : `${labels[key] ?? key} ${value}`,
      )
      .join(' · ')
  }

  async function loadKnowledgeBases(): Promise<void> {
    loadingKnowledgeBases.value = true
    knowledgeBasesError.value = ''
    try {
      if (!auth.activeSpaceId) {
        knowledgeBases.value = []
        activeKnowledgeBaseId.value = ''
        documents.value = []
        return
      }
      knowledgeBases.value = (await fetchKnowledgeBases(auth.activeSpaceId)).items
      const requestedKnowledgeBaseId =
        typeof route.query.knowledge_base_id === 'string' ? route.query.knowledge_base_id : ''
      activeKnowledgeBaseId.value = knowledgeBases.value.some(
        (item) => item.id === requestedKnowledgeBaseId,
      )
        ? requestedKnowledgeBaseId
        : (knowledgeBases.value[0]?.id ?? '')
      if (!activeKnowledgeBaseId.value) documents.value = []
    } catch (cause) {
      knowledgeBasesError.value = cause instanceof Error ? cause.message : '知识库加载失败'
      toast.error(knowledgeBasesError.value)
    } finally {
      loadingKnowledgeBases.value = false
    }
  }

  async function loadDocuments(): Promise<void> {
    if (!activeKnowledgeBaseId.value) {
      documents.value = []
      return
    }
    loading.value = true
    documentsError.value = ''
    try {
      documents.value = (await fetchDocuments(activeKnowledgeBaseId.value)).items
    } catch (cause) {
      documentsError.value = cause instanceof Error ? cause.message : '文档加载失败'
      toast.error(documentsError.value)
    } finally {
      loading.value = false
    }
  }

  function openUpload(): void {
    // 上传是独立任务；关闭未完成的详情读取，避免两个遮罩叠加并露出“正在加载”。
    closeDetail()
    uploadError.value = ''
    uploadOpen.value = true
  }

  async function handleUpload(file: File): Promise<void> {
    if (!activeKnowledgeBaseId.value) return
    uploading.value = true
    uploadError.value = ''
    try {
      await uploadDocument(activeKnowledgeBaseId.value, file)
      uploadOpen.value = false
      toast.success('文档上传成功', '后台解析完成后即可进入构建和发布流程。')
      await loadDocuments()
    } catch (cause) {
      uploadError.value = cause instanceof Error ? cause.message : '上传失败，请稍后重试'
    } finally {
      uploading.value = false
    }
  }

  async function openDetail(document: DocumentRow, preferredVersionId?: string): Promise<void> {
    detailLoading.value = true
    detailChunksLoading.value = false
    detailChunksError.value = ''
    detail.value = null
    detailChunks.value = []
    versionDiff.value = null
    try {
      const data = await fetchDocument(document.id)
      detail.value = data
      detailLoading.value = false

      const selectedVersion =
        data.versions.find((version) => version.id === preferredVersionId) ?? data.versions[0]
      if (selectedVersion) await loadDetailChunks(selectedVersion.id)
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '文档详情加载失败')
      detailLoading.value = false
    }
  }

  /** 对比详情中的最新两个版本，并只展示服务端生成的短摘要。 */
  async function compareLatestVersions(): Promise<void> {
    if (!detail.value || detail.value.versions.length < 2) return
    versionDiffLoading.value = true
    try {
      const [after, before] = detail.value.versions
      versionDiff.value = await compareDocumentVersions(
        detail.value.document.id,
        before.id,
        after.id,
      )
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '版本对比失败')
    } finally {
      versionDiffLoading.value = false
    }
  }

  /** 重新解析当前文档；嵌入重建由知识库构建入口负责。 */
  async function requestReparse(): Promise<void> {
    if (!detail.value) return
    try {
      await reparseDocument(detail.value.document.id)
      toast.success('已重新排队解析', '解析完成后可从知识库构建入口重新生成嵌入。')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '重新解析失败')
    }
  }

  async function requestRebuild(): Promise<void> {
    if (!detail.value) return
    try {
      await rebuildKnowledgeBase(detail.value.document.knowledge_base_id)
      toast.success('已创建嵌入构建任务', '后台将重新生成当前知识库索引。')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '重新嵌入失败')
    }
  }

  async function loadDetailChunks(versionId: string): Promise<void> {
    detailChunksLoading.value = true
    detailChunksError.value = ''
    let timeoutId: number | undefined
    try {
      const previewPromise = fetchVersionPreview(versionId)
      const timeoutPromise = new Promise<never>((_, reject) => {
        timeoutId = window.setTimeout(
          () => reject(new Error('切片预览请求超时，请检查后台解析任务状态')),
          5000,
        )
      })
      const preview = await Promise.race([previewPromise, timeoutPromise])
      detailChunks.value = preview.chunks
      highlightedChunkId.value =
        typeof route.query.chunk_id === 'string' ? route.query.chunk_id : ''
      await nextTick()
      if (highlightedChunkId.value) {
        window.document
          .querySelector(`[data-chunk-id="${highlightedChunkId.value}"]`)
          ?.scrollIntoView({ block: 'center' })
      }
    } catch (cause) {
      detailChunksError.value = cause instanceof Error ? cause.message : '切片预览加载失败'
      toast.error(detailChunksError.value)
    } finally {
      if (timeoutId !== undefined) window.clearTimeout(timeoutId)
      detailChunksLoading.value = false
    }
  }

  /** 关闭详情并清空异步读取状态，确保弹框不会因 loading 标记再次保持打开。 */
  function closeDetail(): void {
    detail.value = null
    detailLoading.value = false
    detailChunks.value = []
    detailChunksError.value = ''
    detailChunksLoading.value = false
    versionDiff.value = null
    highlightedChunkId.value = ''
  }

  /** 在新标签页打开受保护下载地址，服务端负责 Session/租户/发布版本鉴权。 */
  function downloadVersion(versionId: string): void {
    window.open(documentVersionDownloadUrl(versionId), '_blank', 'noopener,noreferrer')
  }

  /** 打开停用确认框，真正的状态变更只在确认事件中发生。 */
  function requestDisable(document: DocumentRow): void {
    pendingDocumentAction.value = { document, action: 'disable' }
  }

  /** 打开删除确认框，历史用量和审计记录由服务端保留。 */
  function requestRemove(document: DocumentRow): void {
    pendingDocumentAction.value = { document, action: 'remove' }
  }

  /** 执行已经确认的文档生命周期操作，并刷新列表作为唯一事实来源。 */
  async function confirmDocumentAction(): Promise<void> {
    const pending = pendingDocumentAction.value
    if (!pending) return
    const document = pending.document
    busyDocumentId.value = document.id
    try {
      if (pending.action === 'disable') {
        await disableDocument(document.id)
        toast.success('文档已停用', '它不会进入新的发布版本。')
      } else {
        await deleteDocument(document.id)
        toast.success('文档已删除', '文档已从列表隐藏，历史记录仍会保留。')
      }
      pendingDocumentAction.value = null
      await loadDocuments()
    } catch (cause) {
      toast.error(
        cause instanceof Error
          ? cause.message
          : pending.action === 'disable'
            ? '停用失败'
            : '删除失败',
      )
    } finally {
      busyDocumentId.value = null
    }
  }

  function parseStatusLabel(status: string): string {
    return (
      {
        complete: '解析完成',
        partial: '部分完成',
        processing: '解析中',
        queued: '等待处理',
        failed: '解析失败',
        unsupported: '不支持',
      }[status] ?? status
    )
  }

  function formatDate(value: string): string {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  }

  watch(activeKnowledgeBaseId, loadDocuments)
  watch(() => auth.activeSpaceId, loadKnowledgeBases, { immediate: true })
  watch(
    [documents, () => route.fullPath],
    async () => {
      const documentId = typeof route.query.document_id === 'string' ? route.query.document_id : ''
      const versionId =
        typeof route.query.version_id === 'string' ? route.query.version_id : undefined
      if (!documentId) return
      const citationKey = `${documentId}:${versionId ?? ''}:${String(route.query.chunk_id ?? '')}`
      if (citationKey === openedCitationKey) return
      const target = documents.value.find((document) => document.id === documentId)
      if (!target) return
      openedCitationKey = citationKey
      await openDetail(target, versionId)
    },
    { immediate: true },
  )

  watch(
    () => route.query.knowledge_base_id,
    (value) => {
      if (typeof value === 'string' && knowledgeBases.value.some((item) => item.id === value))
        activeKnowledgeBaseId.value = value
    },
  )
  return {
    knowledgeBases,
    activeKnowledgeBaseId,
    documents,
    searchQuery,
    statusFilter,
    loading,
    loadingKnowledgeBases,
    knowledgeBasesError,
    documentsError,
    uploadError,
    uploadOpen,
    uploading,
    busyDocumentId,
    detail,
    detailChunks,
    detailLoading,
    detailChunksLoading,
    detailChunksError,
    versionDiff,
    versionDiffLoading,
    highlightedChunkId,
    pendingDocumentAction,
    visibleDocuments,
    activeKnowledgeBase,
    purposeLabels,
    formatLocator,
    loadKnowledgeBases,
    loadDocuments,
    openUpload,
    handleUpload,
    openDetail,
    compareLatestVersions,
    requestReparse,
    requestRebuild,
    loadDetailChunks,
    closeDetail,
    downloadVersion,
    requestDisable,
    requestRemove,
    confirmDocumentAction,
    parseStatusLabel,
    formatDate,
  }
}
