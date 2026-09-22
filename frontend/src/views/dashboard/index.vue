<!-- 工作台视图只负责布局与组件编排，数据请求和派生状态由同目录逻辑模块维护。 -->
<script setup lang="ts">
import { ArrowUpRight, Bot, FileText, Layers3, ListChecks, Plus } from '@/components'
import { useDashboardPage } from './index'

const {
  currentSpace,
  knowledgeBases,
  currentKnowledgeBase,
  documentCount,
  activeTasks,
  pendingTaskCount,
  loading,
  serviceReady,
} = useDashboardPage()
</script>

<template>
  <section class="mx-auto w-full max-w-[1160px]">
    <div class="page-intro">
      <div>
        <p class="eyebrow">{{ currentSpace?.name || '客户空间' }} / 概览</p>
        <h1>工作台</h1>
        <p class="page-description">
          管理你的知识内容，查看处理状态，并从已发布资料中获得可追溯答案。
        </p>
      </div>
      <RouterLink class="primary-button" to="/documents"><Plus :size="16" />上传文档</RouterLink>
    </div>
    <div v-if="loading" class="content-card module-placeholder mb-[20px] min-h-[170px]">
      <span class="loading-spinner" />
      <p>正在加载工作台…</p>
    </div>
    <div v-else class="mb-[20px] grid grid-cols-2 gap-[10px] lg:grid-cols-4">
      <div class="flex items-start gap-[12px] rounded-lg border border-border bg-card p-[16px]">
        <div class="grid size-[34px] place-items-center rounded-md bg-primary/10 text-primary">
          <Layers3 :size="19" />
        </div>
        <div>
          <span class="block text-[11px] text-muted-foreground">知识库</span>
          <strong class="my-[2px] block text-[21px] leading-tight">{{
            knowledgeBases.length
          }}</strong>
          <small class="block text-[10px] text-muted-foreground">当前空间可用</small>
        </div>
      </div>
      <div class="flex items-start gap-[12px] rounded-lg border border-border bg-card p-[16px]">
        <div class="grid size-[34px] place-items-center rounded-md bg-secondary text-primary">
          <FileText :size="19" />
        </div>
        <div>
          <span class="block text-[11px] text-muted-foreground">文档</span>
          <strong class="my-[2px] block text-[21px] leading-tight">{{ documentCount }}</strong>
          <small class="block text-[10px] text-muted-foreground">当前空间可用</small>
        </div>
      </div>
      <div class="flex items-start gap-[12px] rounded-lg border border-border bg-card p-[16px]">
        <div
          class="grid size-[34px] place-items-center rounded-md bg-status-warning-soft text-status-warning"
        >
          <ListChecks :size="19" />
        </div>
        <div>
          <span class="block text-[11px] text-muted-foreground">待处理任务</span>
          <strong class="my-[2px] block text-[21px] leading-tight">{{ pendingTaskCount }}</strong>
          <small class="block text-[10px] text-muted-foreground">{{
            pendingTaskCount ? '解析或构建正在进行' : '当前没有运行中的任务'
          }}</small>
        </div>
      </div>
      <div class="flex items-start gap-[12px] rounded-lg border border-border bg-card p-[16px]">
        <div
          class="grid size-[34px] place-items-center rounded-md bg-status-up-soft text-status-up"
        >
          <Bot :size="19" />
        </div>
        <div>
          <span class="block text-[11px] text-muted-foreground">基础服务</span>
          <strong class="my-[4px] block text-[17px] leading-tight text-status-up">{{
            serviceReady === true ? '正常' : serviceReady === false ? '异常' : '未知'
          }}</strong>
          <small class="block text-[10px] text-muted-foreground">数据库、队列与文件存储</small>
        </div>
      </div>
    </div>
    <div v-if="!loading" class="mb-[18px] grid gap-[20px] lg:grid-cols-[1.15fr_0.85fr]">
      <section class="content-card">
        <div class="mb-[19px] flex items-start justify-between gap-[16px]">
          <div>
            <p class="eyebrow">内容管理</p>
            <h2>知识库</h2>
          </div>
          <RouterLink
            class="inline-flex items-center gap-[4px] text-[11px] text-muted-foreground hover:text-foreground"
            to="/knowledge-bases"
          >
            查看全部
            <ArrowUpRight :size="15" />
          </RouterLink>
        </div>
        <div v-if="currentKnowledgeBase" class="flex items-center gap-[12px]">
          <div
            class="grid size-[38px] shrink-0 place-items-center rounded-lg bg-primary/10 text-base font-semibold text-primary"
          >
            {{ currentKnowledgeBase.name.slice(0, 1) }}
          </div>
          <div class="min-w-0 flex-1">
            <strong class="block text-[13px]">{{ currentKnowledgeBase.name }}</strong>
            <span class="mt-[2px] block text-[11px] text-muted-foreground">{{
              currentKnowledgeBase.description || '暂无知识库说明'
            }}</span>
            <div class="mt-[6px] flex items-center gap-[8px]">
              <span
                class="rounded bg-status-up-soft px-[6px] py-[2px] text-[10px] text-status-up"
                >{{
                  currentKnowledgeBase.status === 'published'
                    ? '已发布'
                    : currentKnowledgeBase.status === 'indexing'
                      ? '构建中'
                      : '草稿'
                }}</span
              >
              <small class="text-[10px] text-muted-foreground"
                >更新于
                {{ new Date(currentKnowledgeBase.updated_at).toLocaleDateString('zh-CN') }}</small
              >
            </div>
          </div>
          <div class="text-right">
            <strong class="block text-[22px] leading-tight">{{
              currentKnowledgeBase.document_count
            }}</strong>
            <span class="text-[10px] text-muted-foreground">篇文档</span>
          </div>
        </div>
        <div v-else class="empty-state compact">
          <div class="empty-icon">
            <Layers3 :size="18" />
          </div>
          <strong>还没有知识库</strong><span>创建知识库后，这里会显示当前空间的内容概览。</span>
        </div>
        <div class="my-[20px] h-px bg-border" />
        <div class="flex flex-wrap gap-[8px]">
          <RouterLink
            class="inline-flex items-center gap-[6px] rounded-md border border-border bg-secondary px-[10px] py-[6px] text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
            to="/documents"
            ><FileText :size="16" />文档管理</RouterLink
          >
          <RouterLink
            class="inline-flex items-center gap-[6px] rounded-md border border-border bg-secondary px-[10px] py-[6px] text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
            to="/chat"
            ><Bot :size="16" />开始问答</RouterLink
          >
          <RouterLink
            class="inline-flex items-center gap-[6px] rounded-md border border-border bg-secondary px-[10px] py-[6px] text-[11px] text-muted-foreground hover:border-primary hover:text-foreground"
            to="/releases"
            ><Layers3 :size="16" />发布版本</RouterLink
          >
        </div>
      </section>
      <section class="content-card">
        <div class="mb-[19px] flex items-start justify-between gap-[16px]">
          <div>
            <p class="eyebrow">最近动态</p>
            <h2>任务状态</h2>
          </div>
          <RouterLink
            class="inline-flex items-center gap-[4px] text-[11px] text-muted-foreground hover:text-foreground"
            to="/tasks"
          >
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
        <div v-else class="flex flex-col gap-[6px]">
          <div
            v-for="task in activeTasks.slice(0, 3)"
            :key="task.id"
            class="flex items-center gap-[8px] rounded-md border border-border bg-secondary px-[10px] py-[8px]"
          >
            <span
              class="size-[6px] shrink-0 rounded-full"
              :class="task.state === 'running' ? 'bg-primary' : 'bg-status-warning'"
            />
            <div class="flex min-w-0 flex-1 flex-col">
              <strong class="text-[11px] font-semibold">{{
                task.task_type === 'document_parse' ? '文档解析' : task.task_type
              }}</strong>
              <small class="mt-[2px] text-[10px] text-muted-foreground"
                >{{ task.completed_items }} / {{ task.item_count || 1 }} 项完成</small
              >
            </div>
            <span class="text-[10px] text-muted-foreground">{{
              task.state === 'running' ? '处理中' : '排队中'
            }}</span>
          </div>
        </div>
      </section>
    </div>
    <div
      class="flex items-center gap-[12px] rounded-md border border-primary/20 bg-primary/5 px-[14px] py-[12px] text-primary max-sm:flex-col max-sm:items-start max-sm:gap-[6px]"
    >
      <span class="shrink-0 text-[11px] font-semibold">试点提示</span>
      <p class="mb-0 flex-1 text-[11px] text-primary/80">
        当前工作空间使用公司内网模型服务。回答仅基于已发布资料，无法找到证据时会明确提示资料不足。
      </p>
      <RouterLink
        class="inline-flex items-center gap-[4px] text-[11px] font-semibold text-primary"
        to="/chat"
      >
        去提问
        <ArrowUpRight :size="14" />
      </RouterLink>
    </div>
  </section>
</template>
