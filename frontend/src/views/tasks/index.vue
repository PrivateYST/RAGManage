<script setup lang="ts">
import type { KnowledgeBaseRow } from '@/api/admin'
import type { TaskRow } from '@/api/documents'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '@/api/admin'
import { cancelTask, fetchTasks, retryTask } from '@/api/documents'
import { Ban, CheckCircle2, Clock3, ListChecks, RefreshCw, RotateCcw, XCircle } from '@/components'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const knowledgeBases = ref<KnowledgeBaseRow[]>([])
const tasks = ref<TaskRow[]>([])
const knowledgeBaseId = shallowRef('all')
const stateFilter = shallowRef('all')
const loading = shallowRef(true)
const error = shallowRef('')
const busyTaskId = shallowRef<string | null>(null)

const visibleTasks = computed(() =>
  tasks.value.filter((task) => {
    const matchesKnowledgeBase =
      knowledgeBaseId.value === 'all' || task.knowledge_base_id === knowledgeBaseId.value
    const matchesState = stateFilter.value === 'all' || task.state === stateFilter.value
    return matchesKnowledgeBase && matchesState
  }),
)
const knowledgeBaseNames = computed(
  () => new Map(knowledgeBases.value.map((item) => [item.id, item.name])),
)

const stateLabels: Record<string, string> = {
  queued: '排队中',
  running: '处理中',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

function stateLabel(value: string): string {
  return stateLabels[value] ?? value
}

function taskLabel(value: string): string {
  return (
    { document_parse: '文档解析', document_embed: '文档嵌入', index_build: '索引构建' }[value] ??
    value
  )
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function progress(task: TaskRow): string {
  if (!task.item_count) return task.state === 'completed' ? '已完成' : '—'
  return `${task.completed_items} / ${task.item_count}`
}

async function loadData(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    if (!auth.activeSpaceId) {
      knowledgeBases.value = []
      tasks.value = []
      return
    }
    const [kbResponse, taskResponse] = await Promise.all([
      fetchKnowledgeBases(auth.activeSpaceId),
      fetchTasks({ tenantId: auth.activeSpaceId }),
    ])
    knowledgeBases.value = kbResponse.items
    tasks.value = taskResponse.items
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '任务加载失败'
  } finally {
    loading.value = false
  }
}

async function handleRetry(task: TaskRow): Promise<void> {
  busyTaskId.value = task.id
  error.value = ''
  try {
    await retryTask(task.id)
    await loadData()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '任务重试失败'
  } finally {
    busyTaskId.value = null
  }
}

async function handleCancel(task: TaskRow): Promise<void> {
  busyTaskId.value = task.id
  error.value = ''
  try {
    await cancelTask(task.id)
    await loadData()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '任务取消失败'
  } finally {
    busyTaskId.value = null
  }
}

watch(
  () => auth.activeSpaceId,
  async () => {
    knowledgeBaseId.value = 'all'
    await loadData()
  },
  { immediate: true },
)

watch(knowledgeBaseId, async (value, previousValue) => {
  if (value === previousValue || !auth.activeSpaceId) return
  loading.value = true
  error.value = ''
  try {
    tasks.value = (
      await fetchTasks({
        tenantId: auth.activeSpaceId,
        ...(value === 'all' ? {} : { knowledgeBaseId: value }),
      })
    ).items
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '任务加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <section class="page-section tasks-page">
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
    <div v-if="error" class="error-banner">
      {{ error }}
    </div>
    <div class="content-card task-filter-card">
      <label
        >知识库<select v-model="knowledgeBaseId">
          <option value="all">全部知识库</option>
          <option
            v-for="knowledgeBase in knowledgeBases"
            :key="knowledgeBase.id"
            :value="knowledgeBase.id"
          >
            {{ knowledgeBase.name }}
          </option>
        </select></label
      >
      <label
        >状态<select v-model="stateFilter">
          <option value="all">全部状态</option>
          <option value="queued">排队中</option>
          <option value="running">处理中</option>
          <option value="completed">已完成</option>
          <option value="failed">失败</option>
          <option value="cancelled">已取消</option>
        </select></label
      >
      <span class="table-count">共 {{ visibleTasks.length }} 个任务</span>
    </div>
    <div v-if="loading" class="content-card module-placeholder">
      <span class="loading-spinner" />
      <p>正在加载任务…</p>
    </div>
    <div v-else class="content-card table-card task-table-card">
      <table>
        <thead>
          <tr>
            <th>任务</th>
            <th>知识库</th>
            <th>状态</th>
            <th>进度</th>
            <th>尝试次数</th>
            <th>创建时间</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody v-if="visibleTasks.length">
          <tr v-for="task in visibleTasks" :key="task.id">
            <td>
              <div class="task-name">
                <span class="task-type-icon" :class="task.state"
                  ><CheckCircle2 v-if="task.state === 'completed'" :size="14" /><XCircle
                    v-else-if="task.state === 'failed'"
                    :size="14" /><Clock3 v-else :size="14"
                /></span>
                <div>
                  <strong>{{ taskLabel(task.task_type) }}</strong
                  ><small>#{{ task.id }}</small>
                </div>
              </div>
            </td>
            <td>
              {{
                task.knowledge_base_id ? knowledgeBaseNames.get(task.knowledge_base_id) || '—' : '—'
              }}
            </td>
            <td>
              <span class="status-pill" :class="task.state">{{ stateLabel(task.state) }}</span>
            </td>
            <td>{{ progress(task) }}</td>
            <td>{{ task.attempt }}</td>
            <td>{{ formatDate(task.created_at) }}</td>
            <td>{{ formatDate(task.updated_at) }}</td>
            <td class="task-actions-cell">
              <button
                v-if="['failed', 'cancelled', 'interrupted'].includes(task.state)"
                class="table-action task-action-button"
                type="button"
                :disabled="busyTaskId === task.id"
                @click="handleRetry(task)"
              >
                <RotateCcw :size="13" aria-hidden="true" />重试
              </button>
              <button
                v-else-if="['queued', 'running'].includes(task.state)"
                class="table-action task-action-button"
                type="button"
                :disabled="busyTaskId === task.id"
                @click="handleCancel(task)"
              >
                <Ban :size="13" aria-hidden="true" />取消
              </button>
              <span v-else class="muted-action">—</span>
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <td colspan="8">
              <div class="empty-state compact">
                <div class="empty-icon">
                  <ListChecks :size="18" />
                </div>
                <strong>暂无任务</strong><span>上传文档后，解析任务会显示在这里。</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
