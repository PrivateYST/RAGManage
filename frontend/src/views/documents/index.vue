<!-- 文档管理工作区：协调知识库筛选、AppTable 列表、上传和非阻塞详情卡片。 -->
<script setup lang="ts">
import type { KnowledgeBaseRow } from '@/api/admin'
import type { ChunkRow, DocumentDetail, DocumentRow } from '@/api/documents'
import { computed, nextTick, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { fetchKnowledgeBases } from '@/api/admin'
import {
  deleteDocument,
  disableDocument,
  fetchDocument,
  fetchDocuments,
  fetchVersionPreview,
  uploadDocument,
} from '@/api/documents'
import { AppConfirmDialog, AppDialog, FileText, Plus, RefreshCw, X } from '@/components'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'
import DocumentFilters from '@/views/documents/components/DocumentFilters.vue'
import DocumentTable from '@/views/documents/components/DocumentTable.vue'
import UploadDialog from '@/views/documents/components/UploadDialog.vue'

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
const uploadError = shallowRef('')
const uploadOpen = shallowRef(false)
const uploading = shallowRef(false)
const busyDocumentId = shallowRef<string | null>(null)
const detail = ref<DocumentDetail | null>(null)
const detailChunks = ref<ChunkRow[]>([])
const detailLoading = shallowRef(false)
const detailChunksLoading = shallowRef(false)
const detailChunksError = shallowRef('')
const highlightedChunkId = shallowRef('')
const pendingDocumentAction = shallowRef<{
  document: DocumentRow
  action: 'disable' | 'remove'
} | null>(null)
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

const purposeLabels: Record<string, string> = {
  general: '通用知识',
  product: '产品说明',
  troubleshooting: '故障排查',
  rule: '业务规则',
}

async function loadKnowledgeBases(): Promise<void> {
  loadingKnowledgeBases.value = true
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
    toast.error(cause instanceof Error ? cause.message : '知识库加载失败')
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
  try {
    documents.value = (await fetchDocuments(activeKnowledgeBaseId.value)).items
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '文档加载失败')
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
    highlightedChunkId.value = typeof route.query.chunk_id === 'string' ? route.query.chunk_id : ''
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
  highlightedChunkId.value = ''
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
</script>

<template>
  <section class="mx-auto w-full max-w-[1160px] pb-[28px]">
    <div class="page-intro">
      <div>
        <p class="eyebrow">知识库管理</p>
        <h1>文档管理</h1>
        <p class="page-description">上传资料、确认解析结果，并在发布前检查原文定位和处理告警。</p>
      </div>
      <button
        class="primary-button"
        type="button"
        :disabled="!activeKnowledgeBaseId"
        @click="openUpload"
      >
        <Plus :size="16" aria-hidden="true" />上传文档
      </button>
    </div>

    <div
      class="content-card mb-[12px] flex items-center justify-between gap-[18px] px-[18px] py-[15px] max-sm:items-start max-sm:flex-col"
    >
      <div class="flex min-w-0 items-center gap-[10px]">
        <span
          class="grid size-[27px] shrink-0 place-items-center rounded-md bg-primary/10 text-primary"
          ><FileText :size="14" aria-hidden="true"
        /></span>
        <div class="flex min-w-0 flex-col gap-[2px]">
          <span class="eyebrow mb-0 text-[10px]">当前知识库</span>
          <strong class="truncate text-[13px]">{{
            activeKnowledgeBase?.name || '请选择知识库'
          }}</strong>
          <small class="text-[10px] text-muted-foreground">{{
            activeKnowledgeBase
              ? purposeLabels[activeKnowledgeBase.purpose] || activeKnowledgeBase.purpose
              : '登录用户暂无可访问知识库'
          }}</small>
        </div>
      </div>
      <label
        class="flex items-center gap-[8px] text-[11px] text-muted-foreground max-sm:w-full max-sm:justify-between"
      >
        <span>切换知识库</span>
        <select
          v-model="activeKnowledgeBaseId"
          class="h-[34px] min-w-[180px] rounded-md border border-border bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 max-sm:min-w-0 max-sm:flex-1"
          :disabled="loadingKnowledgeBases"
          aria-label="切换知识库"
        >
          <option v-if="!knowledgeBases.length" value="">暂无可用知识库</option>
          <option
            v-for="knowledgeBase in knowledgeBases"
            :key="knowledgeBase.id"
            :value="knowledgeBase.id"
          >
            {{ knowledgeBase.name }}
          </option>
        </select>
      </label>
    </div>

    <DocumentFilters
      v-model:query="searchQuery"
      v-model:status="statusFilter"
      :count="visibleDocuments.length"
    />

    <div v-if="loading" class="content-card module-placeholder document-loading">
      <span class="loading-spinner" />
      <p>正在加载文档…</p>
    </div>
    <DocumentTable
      v-else
      :documents="visibleDocuments"
      :busy-id="busyDocumentId"
      @preview="openDetail"
      @disable="requestDisable"
      @remove="requestRemove"
    />

    <div class="mt-[12px] flex items-center gap-[6px] text-[10px] text-muted-foreground">
      <RefreshCw :size="14" aria-hidden="true" />
      <span>新版本不会覆盖已发布版本；解析失败时，旧发布内容仍然保持可用。</span>
    </div>
  </section>

  <UploadDialog
    :open="uploadOpen"
    :busy="uploading"
    :error="uploadError"
    @close="uploadOpen = false"
    @upload="handleUpload"
  />

  <AppConfirmDialog
    :open="Boolean(pendingDocumentAction)"
    :title="
      pendingDocumentAction?.action === 'disable'
        ? `确定停用“${pendingDocumentAction.document.title}”？`
        : `确定删除“${pendingDocumentAction?.document.title ?? ''}”？`
    "
    :description="
      pendingDocumentAction?.action === 'disable'
        ? '停用后文档不会进入新的发布版本。'
        : '删除后文档将从列表隐藏，历史记录仍会保留。'
    "
    :confirm-label="pendingDocumentAction?.action === 'disable' ? '确认停用' : '确认删除'"
    :busy="Boolean(pendingDocumentAction && busyDocumentId === pendingDocumentAction.document.id)"
    @update:open="(open) => !open && (pendingDocumentAction = null)"
    @confirm="confirmDocumentAction"
  />

  <!-- 文档预览由统一 AppDialog 承载，避免按钮打开自制页面内弹层而绕过焦点管理。 -->
  <AppDialog
    :open="Boolean(detail || detailLoading)"
    title="文档详情"
    description="查看文档版本、解析告警与切片预览。"
    content-class="w-[min(760px,calc(100vw-2rem))]"
    @close="closeDetail"
  >
    <section
      class="dialog-card document-detail-dialog w-full max-w-[720px]"
      aria-labelledby="document-detail-title"
    >
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">文档详情</p>
          <h2 id="document-detail-title">
            {{ detail?.document.title || '正在加载…' }}
          </h2>
        </div>
        <button class="dialog-close" type="button" aria-label="关闭详情" @click="closeDetail">
          <X :size="16" />
        </button>
      </div>
      <div v-if="detailLoading" class="module-placeholder detail-loading">
        <span class="loading-spinner" />
        <p>正在读取版本和切片…</p>
      </div>
      <template v-else-if="detail">
        <div class="mb-[12px] flex gap-[18px] text-[11px] text-muted-foreground">
          <span
            >状态：{{
              detail.document.status === 'active'
                ? '启用'
                : detail.document.status === 'disabled'
                  ? '停用'
                  : '已删除'
            }}</span
          ><span>版本数：{{ detail.versions.length }}</span>
        </div>
        <div class="flex max-h-[150px] flex-col gap-[6px] overflow-y-auto pr-[4px]">
          <div
            v-for="version in detail.versions"
            :key="version.id"
            class="flex items-center justify-between gap-[14px] rounded-md border border-border bg-secondary px-[10px] py-[8px]"
          >
            <div>
              <strong class="text-xs text-foreground">V{{ version.version_no }}</strong>
              <small class="mt-[2px] block text-[10px] text-muted-foreground"
                >{{ formatDate(version.created_at) }} ·
                {{ version.file_size.toLocaleString() }} bytes</small
              >
            </div>
            <span
              class="inline-flex min-h-[20px] items-center rounded-full px-[8px] text-[10px] font-medium"
              :class="
                version.parse_status === 'complete'
                  ? 'bg-status-up-soft text-status-up'
                  : version.parse_status === 'failed'
                    ? 'bg-destructive/10 text-destructive'
                    : 'bg-status-warning-soft text-status-warning'
              "
              >{{ parseStatusLabel(version.parse_status) }}</span
            >
          </div>
        </div>
        <div
          v-if="detail.versions[0]?.warnings.length"
          class="mt-[12px] flex flex-col gap-[2px] rounded-md border border-status-warning/30 bg-status-warning-soft px-[10px] py-[8px] text-[10px] text-status-warning"
        >
          <strong class="text-[11px]">解析告警</strong>
          <span v-for="warning in detail.versions[0].warnings" :key="warning">{{ warning }}</span>
        </div>
        <div class="mt-[15px] min-h-0">
          <div class="mb-[8px] flex items-center justify-between text-xs text-foreground">
            <strong>切片预览</strong
            ><span class="text-[10px] text-muted-foreground">{{ detailChunks.length }} 个切片</span>
          </div>
          <div
            v-if="detailChunksLoading"
            class="flex min-h-[90px] items-center justify-center gap-[8px] text-[11px] text-muted-foreground"
          >
            <span class="loading-spinner" /><span>正在读取切片…</span>
          </div>
          <div
            v-else-if="detailChunksError"
            class="min-h-[90px] rounded-md border border-status-warning/30 bg-status-warning-soft p-[12px] text-[11px] text-status-warning"
          >
            {{ detailChunksError }}
          </div>
          <div v-else-if="detailChunks.length" class="max-h-[300px] overflow-y-auto pr-[4px]">
            <article
              v-for="chunk in detailChunks"
              :key="chunk.id"
              class="rounded-md border border-border p-[10px]"
              :class="{ 'citation-target': chunk.id === highlightedChunkId }"
              :data-chunk-id="chunk.id"
            >
              <div class="flex items-center gap-[8px] text-[10px] text-primary">
                <span>#{{ chunk.ordinal + 1 }}</span>
                <span v-if="chunk.section_path.length">{{ chunk.section_path.join(' / ') }}</span>
                <code class="ml-auto text-[9px] text-muted-foreground">{{
                  Object.entries(chunk.locator)
                    .map(([key, value]) => `${key} ${value}`)
                    .join(' · ')
                }}</code>
              </div>
              <p
                class="mt-[6px] whitespace-pre-wrap text-[11px] leading-[1.65] text-muted-foreground"
              >
                {{ chunk.content }}
              </p>
            </article>
          </div>
          <div v-else class="empty-state compact">
            <strong>暂无可预览切片</strong><span>解析完成后会显示原文定位。</span>
          </div>
        </div>
      </template>
    </section>
  </AppDialog>
</template>
