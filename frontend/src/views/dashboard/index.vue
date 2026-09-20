<script setup lang="ts">
import type { KnowledgeBaseRow } from '@/api/admin'
import type { TaskRow } from '@/api/documents'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '@/api/admin'
import { fetchTasks } from '@/api/documents'
import { fetchHealth } from '@/api/health'
import { ArrowUpRight, Bot, FileText, Layers3, ListChecks, Plus } from '@/components'
import { useAuthStore } from '@/store/auth'

const auth = useAuthStore()
const currentSpace = computed(() => auth.activeSpace)
const knowledgeBases = ref<KnowledgeBaseRow[]>([])
const tasks = ref<TaskRow[]>([])
const loading = shallowRef(true)
const error = shallowRef('')
const serviceReady = shallowRef<boolean | null>(null)

const currentKnowledgeBase = computed(() => knowledgeBases.value[0])
const documentCount = computed(() =>
  knowledgeBases.value.reduce((total, item) => total + item.document_count, 0),
)
const activeTasks = computed(() =>
  tasks.value.filter(task => ['queued', 'running'].includes(task.state)),
)
const pendingTaskCount = computed(() => activeTasks.value.length)

async function loadDashboard(): Promise<void> {
  if (!currentSpace.value) {
    loading.value = false
    return
  }
  loading.value = true
  error.value = ''
  const controller = new AbortController()
  try {
    const [knowledgeBaseResponse, taskResponse, health] = await Promise.all([
      fetchKnowledgeBases(currentSpace.value.id),
      fetchTasks({ tenantId: currentSpace.value.id }),
      fetchHealth(controller.signal),
    ])
    knowledgeBases.value = knowledgeBaseResponse.items
    tasks.value = taskResponse.items
    serviceReady.value = health.status === 'ready'
  }
  catch (cause) {
    error.value = cause instanceof Error ? cause.message : '工作台数据加载失败'
  }
  finally {
    controller.abort()
    loading.value = false
  }
}

watch(() => auth.activeSpaceId, loadDashboard, { immediate: true })
</script>

<template>
  <section class="page-section">
    <div class="page-intro">
      <div>
        <p class="eyebrow">
          {{ currentSpace?.name || '客户空间' }} / 概览
        </p>
        <h1>工作台</h1>
        <p class="page-description">
          管理你的知识内容，查看处理状态，并从已发布资料中获得可追溯答案。
        </p>
      </div>
      <RouterLink class="primary-button" to="/documents">
        <Plus :size="16" />上传文档
      </RouterLink>
    </div>
    <div v-if="error" class="error-banner">
      {{ error }}
    </div>
    <div v-if="loading" class="content-card module-placeholder dashboard-loading">
      <span class="loading-spinner" />
      <p>正在加载工作台…</p>
    </div>
    <div v-else class="metric-grid">
      <div class="metric-card">
        <div class="metric-icon blue">
          <Layers3 :size="19" />
        </div>
        <div>
          <span>知识库</span><strong>{{ knowledgeBases.length }}</strong><small>当前空间可用</small>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon violet">
          <FileText :size="19" />
        </div>
        <div>
          <span>文档</span><strong>{{ documentCount }}</strong><small>当前空间可用</small>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon amber">
          <ListChecks :size="19" />
        </div>
        <div>
          <span>待处理任务</span><strong>{{ pendingTaskCount }}</strong><small>{{ pendingTaskCount ? '解析或构建正在进行' : '当前没有运行中的任务' }}</small>
        </div>
      </div>
      <div class="metric-card">
        <div class="metric-icon green">
          <Bot :size="19" />
        </div>
        <div>
          <span>基础服务</span><strong class="metric-ok">{{
            serviceReady === true ? '正常' : serviceReady === false ? '异常' : '未知'
          }}</strong><small>数据库、队列与文件存储</small>
        </div>
      </div>
    </div>
    <div v-if="!loading" class="dashboard-grid">
      <section class="content-card">
        <div class="card-heading">
          <div>
            <p class="eyebrow">
              内容管理
            </p>
            <h2>知识库</h2>
          </div>
          <RouterLink class="text-link" to="/knowledge-bases">
            查看全部
            <ArrowUpRight :size="15" />
          </RouterLink>
        </div>
        <div v-if="currentKnowledgeBase" class="kb-summary">
          <div class="kb-avatar">
            {{ currentKnowledgeBase.name.slice(0, 1) }}
          </div>
          <div class="kb-info">
            <strong>{{ currentKnowledgeBase.name }}</strong><span>{{ currentKnowledgeBase.description || '暂无知识库说明' }}</span>
            <div class="kb-tags">
              <span>{{
                currentKnowledgeBase.status === 'published'
                  ? '已发布'
                  : currentKnowledgeBase.status === 'indexing'
                    ? '构建中'
                    : '草稿'
              }}</span><small>更新于
                {{ new Date(currentKnowledgeBase.updated_at).toLocaleDateString('zh-CN') }}</small>
            </div>
          </div>
          <div class="kb-count">
            <strong>{{ currentKnowledgeBase.document_count }}</strong><span>篇文档</span>
          </div>
        </div>
        <div v-else class="empty-state compact">
          <div class="empty-icon">
            <Layers3 :size="18" />
          </div>
          <strong>还没有知识库</strong><span>创建知识库后，这里会显示当前空间的内容概览。</span>
        </div>
        <div class="card-divider" />
        <div class="quick-actions">
          <RouterLink to="/documents">
            <FileText :size="16" />文档管理
          </RouterLink>
          <RouterLink to="/chat">
            <Bot :size="16" />开始问答
          </RouterLink>
          <RouterLink to="/releases">
            <Layers3 :size="16" />发布版本
          </RouterLink>
        </div>
      </section>
      <section class="content-card">
        <div class="card-heading">
          <div>
            <p class="eyebrow">
              最近动态
            </p>
            <h2>任务状态</h2>
          </div>
          <RouterLink class="text-link" to="/tasks">
            任务中心
            <ArrowUpRight :size="15" />
          </RouterLink>
        </div>
        <div v-if="!pendingTaskCount" class="empty-state compact">
          <div class="empty-icon">
            <ListChecks :size="18" />
          </div>
          <strong>暂无运行中的任务</strong><span>上传或更新文档后，处理进度会显示在这里。</span>
        </div>
        <div v-else class="task-summary-list">
          <div v-for="task in activeTasks.slice(0, 3)" :key="task.id" class="task-summary-row">
            <span class="task-status-dot" :class="task.state" />
            <div>
              <strong>{{
                task.task_type === 'document_parse' ? '文档解析' : task.task_type
              }}</strong><small>{{ task.completed_items }} / {{ task.item_count || 1 }} 项完成</small>
            </div>
            <span class="task-state-label">{{
              task.state === 'running' ? '处理中' : '排队中'
            }}</span>
          </div>
        </div>
      </section>
    </div>
    <div class="pilot-note">
      <span>试点提示</span>
      <p>
        当前工作空间使用公司内网模型服务。回答仅基于已发布资料，无法找到证据时会明确提示资料不足。
      </p>
      <RouterLink to="/chat">
        去提问
        <ArrowUpRight :size="14" />
      </RouterLink>
    </div>
  </section>
</template>
