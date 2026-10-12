<!-- 平台运行状态页：只编排聚合指标的加载状态和三个展示子功能。 -->
<script setup lang="ts">
import FileStorageMetrics from './components/FileStorageMetrics/index.vue'
import ModelEndpointMetrics from './components/ModelEndpointMetrics/index.vue'
import TaskMetrics from './components/TaskMetrics/index.vue'
import { useRuntimeStatusPage } from './index'
import './index.scss'

const { errorMessage, loading, metrics, refresh } = useRuntimeStatusPage()
</script>

<template>
  <section class="page-section" aria-labelledby="runtime-status-title">
    <div class="page-intro">
      <div>
        <p class="eyebrow">平台管理 · 运行状态</p>
        <h1 id="runtime-status-title">平台运行状态</h1>
        <p class="page-description">查看任务、模型和存储的聚合运行指标，不展示业务数据明细。</p>
      </div>
      <button class="secondary-button" type="button" :disabled="loading" @click="refresh">
        {{ loading ? '刷新中…' : '重新刷新' }}
      </button>
    </div>
    <div v-if="loading" class="content-card module-placeholder min-h-[180px]" role="status">
      <span class="loading-spinner" />
      <p>正在读取平台指标…</p>
    </div>
    <p
      v-else-if="errorMessage"
      class="rounded-md border border-status-danger/20 bg-status-danger-soft px-[14px] py-[12px] text-sm text-status-danger"
      role="alert"
    >
      {{ errorMessage }}
    </p>
    <div v-else-if="metrics" class="grid gap-[16px] md:grid-cols-3">
      <TaskMetrics :metrics="metrics.tasks" />
      <ModelEndpointMetrics :metrics="metrics.models" />
      <FileStorageMetrics :metrics="metrics.storage" />
    </div>
  </section>
</template>
