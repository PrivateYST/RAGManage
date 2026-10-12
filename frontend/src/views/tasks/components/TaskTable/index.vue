<!-- 任务表格与行操作：展示任务快照，并将重试/取消事件委托给页面。 -->
<script setup lang="ts">
import type { TaskTableEmits, TaskTableProps } from './type'
import { AppTable, Ban, CheckCircle2, Clock3, RotateCcw, XCircle } from '@/components'
import {
  formatTaskDate,
  taskColumns,
  taskIconClass,
  taskProgress,
  taskStateLabel,
  taskStatusClass,
  taskTypeLabel,
} from './index'
import './index.scss'

defineProps<TaskTableProps>()
const emit = defineEmits<TaskTableEmits>()
</script>

<template>
  <div class="content-card table-card overflow-x-auto p-0">
    <AppTable
      :rows="rows"
      :columns="taskColumns"
      row-key="id"
      class="w-full min-w-[840px] text-left"
      empty-text="暂无任务"
    >
      <template #cell-task="{ row }">
        <div class="flex items-center gap-[8px]">
          <span
            class="grid size-[27px] place-items-center rounded-md"
            :class="taskIconClass(row.state)"
          >
            <CheckCircle2 v-if="row.state === 'completed'" :size="14" :aria-hidden="true" />
            <XCircle v-else-if="row.state === 'failed'" :size="14" :aria-hidden="true" />
            <Clock3 v-else :size="14" :aria-hidden="true" />
          </span>
          <span class="flex flex-col">
            <strong class="text-xs font-semibold text-foreground">{{
              taskTypeLabel(row.task_type)
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
          :class="taskStatusClass(row.state)"
          >{{ taskStateLabel(row.state) }}</span
        >
      </template>
      <template #cell-progress="{ row }">{{ taskProgress(row) }}</template>
      <template #cell-created="{ row }">{{ formatTaskDate(row.created_at) }}</template>
      <template #cell-updated="{ row }">{{ formatTaskDate(row.updated_at) }}</template>
      <template #cell-actions="{ row }">
        <button
          v-if="['failed', 'cancelled', 'interrupted'].includes(row.state)"
          class="table-action"
          type="button"
          :disabled="busyTaskId === row.id"
          @click="emit('retry', row)"
        >
          <RotateCcw :size="13" :aria-hidden="true" />重试
        </button>
        <button
          v-else-if="['queued', 'running'].includes(row.state)"
          class="table-action"
          type="button"
          :disabled="busyTaskId === row.id"
          @click="emit('cancel', row)"
        >
          <Ban :size="13" :aria-hidden="true" />取消
        </button>
        <span v-else class="text-[11px] text-muted-foreground/50">—</span>
      </template>
    </AppTable>
  </div>
</template>
