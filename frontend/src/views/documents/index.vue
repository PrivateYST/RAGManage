<!-- 文档管理工作区：协调知识库筛选、AppTable 列表、上传和非阻塞详情卡片。 -->
<script setup lang="ts">
import { AppConfirmDialog, FileText, Plus, RefreshCw } from '@/components'
import DocumentDetailDialog from './components/DocumentDetailDialog/index.vue'
import DocumentFilters from './components/DocumentFilters/index.vue'
import DocumentTable from './components/DocumentTable/index.vue'
import UploadDialog from './components/UploadDialog/index.vue'
import { useDocumentsPage } from './index'
import './index.scss'
const {
  knowledgeBases,
  activeKnowledgeBaseId,
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
  closeDetail,
  downloadVersion,
  requestDisable,
  requestRemove,
  confirmDocumentAction,
  parseStatusLabel,
  formatDate,
} = useDocumentsPage()
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

    <div
      v-if="knowledgeBasesError"
      class="content-card mb-[12px] flex items-center justify-between gap-[12px]"
      role="alert"
    >
      <span class="text-xs text-destructive">{{ knowledgeBasesError }}</span>
      <button class="secondary-button" type="button" @click="loadKnowledgeBases">
        重新加载知识库
      </button>
    </div>

    <div v-if="loading" class="content-card module-placeholder document-loading">
      <span class="loading-spinner" />
      <p>正在加载文档…</p>
    </div>
    <div
      v-else-if="documentsError"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px]"
      role="alert"
    >
      <strong class="text-sm text-destructive">文档加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ documentsError }}</p>
      <button class="secondary-button" type="button" @click="loadDocuments">重新加载文档</button>
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

  <DocumentDetailDialog
    :detail="detail"
    :loading="detailLoading"
    :chunks="detailChunks"
    :chunks-loading="detailChunksLoading"
    :chunks-error="detailChunksError"
    :version-diff="versionDiff"
    :version-diff-loading="versionDiffLoading"
    :highlighted-chunk-id="highlightedChunkId"
    :format-locator="formatLocator"
    :parse-status-label="parseStatusLabel"
    :format-date="formatDate"
    @close="closeDetail"
    @reparse="requestReparse"
    @rebuild="requestRebuild"
    @download="downloadVersion"
    @compare="compareLatestVersions"
  />
</template>
