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
import DocumentFilters from '@/views/documents/components/DocumentFilters.vue'
import DocumentTable from '@/views/documents/components/DocumentTable.vue'
import UploadDialog from '@/views/documents/components/UploadDialog.vue'
import { FileText, Plus, RefreshCw, X } from '@/components'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const route = useRoute()
const knowledgeBases = ref<KnowledgeBaseRow[]>([])
const activeKnowledgeBaseId = shallowRef('')
const documents = ref<DocumentRow[]>([])
const searchQuery = shallowRef('')
const statusFilter = shallowRef('all')
const loading = shallowRef(false)
const loadingKnowledgeBases = shallowRef(false)
const error = shallowRef('')
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
  error.value = ''
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
    error.value = cause instanceof Error ? cause.message : '知识库加载失败'
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
  error.value = ''
  try {
    documents.value = (await fetchDocuments(activeKnowledgeBaseId.value)).items
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '文档加载失败'
  } finally {
    loading.value = false
  }
}

function openUpload(): void {
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
  error.value = ''
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
    error.value = cause instanceof Error ? cause.message : '文档详情加载失败'
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
  } finally {
    if (timeoutId !== undefined) window.clearTimeout(timeoutId)
    detailChunksLoading.value = false
  }
}

function closeDetail(): void {
  detail.value = null
  detailChunks.value = []
  detailChunksError.value = ''
  detailChunksLoading.value = false
  highlightedChunkId.value = ''
}

async function handleDisable(document: DocumentRow): Promise<void> {
  // eslint-disable-next-line no-alert
  if (!window.confirm(`确定停用“${document.title}”吗？停用后它不会进入新的发布版本。`)) return
  busyDocumentId.value = document.id
  error.value = ''
  try {
    await disableDocument(document.id)
    await loadDocuments()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '停用失败'
  } finally {
    busyDocumentId.value = null
  }
}

async function handleRemove(document: DocumentRow): Promise<void> {
  // eslint-disable-next-line no-alert
  if (!window.confirm(`确定删除“${document.title}”吗？删除后文档将从列表隐藏。`)) return
  busyDocumentId.value = document.id
  error.value = ''
  try {
    await deleteDocument(document.id)
    await loadDocuments()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '删除失败'
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
  <section class="page-section documents-page">
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

    <div v-if="error" class="error-banner">
      {{ error }}
    </div>

    <div class="content-card documents-context-card">
      <div class="documents-context-copy">
        <span class="kb-avatar small"><FileText :size="14" aria-hidden="true" /></span>
        <div>
          <span class="eyebrow">当前知识库</span>
          <strong>{{ activeKnowledgeBase?.name || '请选择知识库' }}</strong>
          <small>{{
            activeKnowledgeBase
              ? purposeLabels[activeKnowledgeBase.purpose] || activeKnowledgeBase.purpose
              : '登录用户暂无可访问知识库'
          }}</small>
        </div>
      </div>
      <label class="kb-select-label">
        <span>切换知识库</span>
        <select
          v-model="activeKnowledgeBaseId"
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
      @disable="handleDisable"
      @remove="handleRemove"
    />

    <div class="document-footnote">
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

  <div v-if="detail || detailLoading" class="dialog-backdrop" @click.self="closeDetail">
    <section class="dialog-card document-detail-dialog" aria-labelledby="document-detail-title">
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
        <div class="detail-meta">
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
        <div class="version-list">
          <div v-for="version in detail.versions" :key="version.id" class="version-row">
            <div>
              <strong>V{{ version.version_no }}</strong
              ><small
                >{{ formatDate(version.created_at) }} ·
                {{ version.file_size.toLocaleString() }} bytes</small
              >
            </div>
            <span class="status-pill" :class="version.parse_status">{{
              parseStatusLabel(version.parse_status)
            }}</span>
          </div>
        </div>
        <div v-if="detail.versions[0]?.warnings.length" class="warning-box">
          <strong>解析告警</strong>
          <span v-for="warning in detail.versions[0].warnings" :key="warning">{{ warning }}</span>
        </div>
        <div class="chunk-preview">
          <div class="chunk-preview-heading">
            <strong>切片预览</strong><span>{{ detailChunks.length }} 个切片</span>
          </div>
          <div v-if="detailChunksLoading" class="chunk-preview-loading">
            <span class="loading-spinner" /><span>正在读取切片…</span>
          </div>
          <div v-else-if="detailChunksError" class="chunk-preview-error">
            {{ detailChunksError }}
          </div>
          <div v-else-if="detailChunks.length" class="chunk-list">
            <article
              v-for="chunk in detailChunks"
              :key="chunk.id"
              class="chunk-item"
              :class="{ 'citation-target': chunk.id === highlightedChunkId }"
              :data-chunk-id="chunk.id"
            >
              <div class="chunk-item-meta">
                <span>#{{ chunk.ordinal + 1 }}</span
                ><span v-if="chunk.section_path.length">{{ chunk.section_path.join(' / ') }}</span
                ><code>{{
                  Object.entries(chunk.locator)
                    .map(([key, value]) => `${key} ${value}`)
                    .join(' · ')
                }}</code>
              </div>
              <p>{{ chunk.content }}</p>
            </article>
          </div>
          <div v-else class="empty-state compact">
            <strong>暂无可预览切片</strong><span>解析完成后会显示原文定位。</span>
          </div>
        </div>
      </template>
    </section>
  </div>
</template>
