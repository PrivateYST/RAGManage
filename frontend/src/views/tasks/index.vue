<!-- 任务中心视图：只负责筛选控件、任务表格和状态反馈的组合。 -->
<script setup lang="ts">
import type { AppTableColumn } from '@/components'
import { AppTable, Ban, CheckCircle2, Clock3, RefreshCw, RotateCcw, XCircle } from '@/components'
import { useTasksPage } from './index'

const {
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
} = useTasksPage()

function statusClass(state: string): string {
  if (state === 'completed') return 'bg-status-up-soft text-status-up'
  if (['failed', 'cancelled', 'interrupted'].includes(state))
    return 'bg-destructive/10 text-destructive'
  if (state === 'running') return 'bg-primary/10 text-primary'
  return 'bg-status-warning-soft text-status-warning'
}

function iconClass(state: string): string {
  if (state === 'completed') return 'bg-status-up-soft text-status-up'
  if (state === 'failed') return 'bg-destructive/10 text-destructive'
  return 'bg-status-warning-soft text-status-warning'
}

const taskColumns: AppTableColumn<Record<string, unknown>>[] = [
  { key: 'task', title: '任务', cellClass: 'px-[18px] py-[14px]' },
  { key: 'knowledgeBase', title: '知识库', cellClass: 'px-[18px] py-[14px]' },
  { key: 'state', title: '状态', cellClass: 'px-[18px] py-[14px]' },
  { key: 'progress', title: '进度', cellClass: 'px-[18px] py-[14px]' },
  { key: 'attempt', title: '尝试次数', field: 'attempt', cellClass: 'px-[18px] py-[14px]' },
  { key: 'created', title: '创建时间', cellClass: 'px-[18px] py-[14px]' },
  { key: 'updated', title: '更新时间', cellClass: 'px-[18px] py-[14px]' },
  { key: 'actions', title: '操作', cellClass: 'px-[18px] py-[14px]' },
]
</script>

<template>
  <section class="mx-auto w-full max-w-[1160px]">
    <div class="page-intro">
      <div>
        <p class="eyebrow">后台处理</p>
        <h1>任务中心</h1>
        <p class="page-description">查看文档解析、切片和后续构建任务的执行状态与失败信息。</p>
      </div>
      <button class="secondary-button" type="button" :disabled="loading" @click="loadData">
        <RefreshCw :size="15" aria-hidden="true" />刷新
      </button>
    </div>

    <div class="content-card mb-[12px] flex flex-wrap items-center gap-[12px] p-[12px]">
      <label class="flex items-center gap-[8px] text-[11px] text-muted-foreground">
        知识库
        <select
          v-model="knowledgeBaseId"
          class="h-[32px] min-w-[150px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        >
          <option value="all">全部知识库</option>
          <option
            v-for="knowledgeBase in knowledgeBases"
            :key="knowledgeBase.id"
            :value="knowledgeBase.id"
          >
            {{ knowledgeBase.name }}
          </option>
        </select>
      </label>
      <label class="flex items-center gap-[8px] text-[11px] text-muted-foreground">
        状态
        <select
          v-model="stateFilter"
          class="h-[32px] min-w-[120px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        >
          <option value="all">全部状态</option>
          <option value="queued">排队中</option>
          <option value="running">处理中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="cancelled">已取消</option>
        </select>
      </label>
      <span class="ml-auto text-[11px] text-muted-foreground"
        >共 {{ visibleTasks.length }} 个任务</span
      >
    </div>

    <div v-if="loading" class="content-card module-placeholder min-h-[280px]">
      <span class="loading-spinner" />
      <p>正在加载任务…</p>
    </div>
    <div v-else class="content-card table-card overflow-x-auto p-0">
      <AppTable
        :rows="visibleTasks"
        :columns="taskColumns"
        row-key="id"
        class="w-full min-w-[840px] text-left"
        empty-text="暂无任务"
      >
        <template #cell-task="{ row }">
          <div class="flex items-center gap-[8px]">
            <span
              class="grid size-[27px] place-items-center rounded-md"
              :class="iconClass(row.state)"
            >
              <CheckCircle2 v-if="row.state === 'completed'" :size="14" />
              <XCircle v-else-if="row.state === 'failed'" :size="14" />
              <Clock3 v-else :size="14" />
            </span>
            <span class="flex flex-col">
              <strong class="text-xs font-semibold text-foreground">{{
                taskLabel(row.task_type)
              }}</strong>
              <small class="mt-[2px] font-mono text-[10px] text-muted-foreground"
                >#{{ row.id }}</small
              >
            </span>
          </div>
        </template>
        <template #cell-knowledgeBase="{ row }">
          {{ row.knowledge_base_id ? knowledgeBaseNames.get(row.knowledge_base_id) || '—' : '—' }}
        </template>
        <template #cell-state="{ row }">
          <span
            class="inline-flex min-h-[20px] items-center rounded-full px-[8px] text-[10px] font-medium"
            :class="statusClass(row.state)"
            >{{ stateLabel(row.state) }}</span
          >
        </template>
        <template #cell-progress="{ row }">{{ progress(row) }}</template>
        <template #cell-created="{ row }">{{ formatDate(row.created_at) }}</template>
        <template #cell-updated="{ row }">{{ formatDate(row.updated_at) }}</template>
        <template #cell-actions="{ row }">
          <button
            v-if="['failed', 'cancelled', 'interrupted'].includes(row.state)"
            class="table-action"
            type="button"
            :disabled="busyTaskId === row.id"
            @click="handleRetry(row)"
          >
            <RotateCcw :size="13" aria-hidden="true" />重试
          </button>
          <button
            v-else-if="['queued', 'running'].includes(row.state)"
            class="table-action"
            type="button"
            :disabled="busyTaskId === row.id"
            @click="handleCancel(row)"
          >
            <Ban :size="13" aria-hidden="true" />取消
          </button>
          <span v-else class="text-[11px] text-muted-foreground/50">—</span>
        </template>
      </AppTable>
    </div>
  </section>
</template>
