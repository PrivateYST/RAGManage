<!-- 知识库管理页面：组合列表状态、创建弹窗和通用表格。 -->
<script setup lang="ts">
import { AppDialog, AppTable, Plus, Search } from '@/components'
import CreateKnowledgeBaseDialog from './components/CreateKnowledgeBaseDialog/index.vue'
import GovernanceDialog from './components/GovernanceDialog/index.vue'
import WikiDialog from './components/WikiDialog/index.vue'
import { useKnowledgeBasesPage } from './index'
import './index.scss'

const page = useKnowledgeBasesPage()
const { wikiOpen, wikiRow, openWiki } = page
const {
  rows,
  loading,
  loadError,
  dialogOpen,
  saving,
  form,
  columns,
  auth,
  editDialogOpen,
  editSaving,
  editingRow,
  members,
  editForm,
} = page

/** 用户关闭/取消弹窗时直接更新页面响应状态，不触发提交请求。 */
function closeDialog(): void {
  dialogOpen.value = false
}
</script>

<template>
  <section class="page-section">
    <div class="page-intro">
      <div>
        <p class="eyebrow">知识库管理</p>
        <h1>知识库</h1>
        <p class="page-description">按业务用途组织文档、规则和产品资料。</p>
      </div>
      <button class="primary-button" @click="page.openCreateDialog">
        <Plus :size="16" />创建知识库
      </button>
    </div>

    <div v-if="loading" class="content-card module-placeholder">
      <span class="loading-spinner" />
      <p>正在加载数据…</p>
    </div>
    <div
      v-else-if="loadError"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px]"
      role="alert"
    >
      <strong class="text-sm text-destructive">知识库列表加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ loadError }}</p>
      <button class="secondary-button" type="button" @click="page.loadData">重新加载</button>
    </div>
    <div v-else class="content-card table-card">
      <div class="table-toolbar">
        <label class="search-box">
          <Search :size="16" aria-hidden="true" />
          <span class="sr-only">搜索知识库</span>
          <input aria-label="搜索知识库" placeholder="搜索知识库" />
        </label>
        <span class="table-count">共 {{ rows.length }} 个知识库</span>
      </div>
      <AppTable :rows="rows" :columns="columns" row-key="id">
        <template #cell-name="{ row }">
          <div class="table-name">
            <span class="kb-avatar small">库</span><strong>{{ row.name }}</strong>
          </div>
        </template>
        <template #cell-documents="{ row }">{{ row.document_count }} 篇</template>
        <template #cell-business_scenario="{ row }">{{
          row.business_scenario || '未标注'
        }}</template>
        <template #cell-trust_level="{ row }">
          {{ row.trust_level === 'high' ? '高' : row.trust_level === 'low' ? '低' : '中' }}
        </template>
        <template #cell-source_system="{ row }">{{ row.source_system || '未标注' }}</template>
        <template #cell-status="{ row }">
          <span class="status-pill" :class="[row.status]">
            {{ row.status === 'published' ? '已发布' : row.status }}
          </span>
        </template>
        <template #cell-updated="{ row }">{{
          new Date(row.updated_at).toLocaleDateString('zh-CN')
        }}</template>
        <template #cell-actions="{ row }"
          ><div class="flex gap-[6px]">
            <button class="secondary-button" type="button" @click="openWiki(row)">词条管理</button
            ><button class="secondary-button" type="button" @click="page.openGovernanceDialog(row)">
              治理设置
            </button>
          </div></template
        >
      </AppTable>
    </div>
  </section>

  <AppDialog
    :open="dialogOpen"
    title="创建知识库"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="closeDialog"
  >
    <CreateKnowledgeBaseDialog
      :form="form"
      :space-name="auth.activeSpace?.name || '暂无可用空间'"
      :saving="saving"
      @cancel="closeDialog"
      @submit="page.saveKnowledgeBase"
    />
  </AppDialog>
  <AppDialog
    :open="editDialogOpen"
    title="编辑治理元数据"
    content-class="w-[min(520px,calc(100vw-2rem))]"
    @close="editDialogOpen = false"
  >
    <GovernanceDialog
      v-if="editingRow"
      :form="editForm"
      :members="members"
      :saving="editSaving"
      :name="editingRow.name"
      @cancel="editDialogOpen = false"
      @submit="page.saveGovernance"
    />
  </AppDialog>
  <AppDialog
    :open="wikiOpen"
    title="LLM Wiki 词条"
    content-class="w-[min(1440px,calc(100vw-2rem))] overflow-y-hidden"
    @close="wikiOpen = false"
  >
    <WikiDialog
      v-if="wikiRow"
      :open="wikiOpen"
      :knowledge-base-id="wikiRow.id"
      :knowledge-base-name="wikiRow.name"
      @close="wikiOpen = false"
    />
  </AppDialog>
</template>
