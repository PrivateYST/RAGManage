<!-- 任务中心入口：编排页面数据逻辑、筛选子视图和任务表格子视图。 -->
<script setup lang="ts">
import { RefreshCw } from '@/components'
import TaskFilters from './components/TaskFilters/index.vue'
import TaskTable from './components/TaskTable/index.vue'
import { useTasksPage } from './index'
import './index.scss'

const {
  knowledgeBases,
  visibleTasks,
  knowledgeBaseNames,
  knowledgeBaseId,
  stateFilter,
  loading,
  errorMessage,
  busyTaskId,
  loadData,
  handleRetry,
  handleCancel,
} = useTasksPage()
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
        <RefreshCw :size="15" :aria-hidden="true" />刷新
      </button>
    </div>

    <TaskFilters
      v-model:knowledge-base-id="knowledgeBaseId"
      v-model:state-filter="stateFilter"
      :knowledge-bases="knowledgeBases"
      :visible-task-count="visibleTasks.length"
    />

    <div v-if="loading" class="content-card module-placeholder min-h-[280px]" role="status">
      <span class="loading-spinner" />
      <p>正在加载任务…</p>
    </div>
    <div
      v-else-if="errorMessage"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px] text-center"
      role="alert"
    >
      <strong class="text-sm text-destructive">任务加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ errorMessage }}</p>
      <button class="secondary-button" type="button" @click="loadData">重新加载</button>
    </div>
    <TaskTable
      v-else
      :rows="visibleTasks"
      :knowledge-base-names="knowledgeBaseNames"
      :busy-task-id="busyTaskId"
      @retry="handleRetry"
      @cancel="handleCancel"
    />
  </section>
</template>
