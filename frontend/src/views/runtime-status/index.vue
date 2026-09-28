<!-- 平台运行状态页：只展示后端聚合指标，不暴露租户、正文或凭据明细。 -->
<script setup lang="ts">
import type { RuntimeMetrics } from '@/api/health'
import { onMounted, onUnmounted, ref } from 'vue'
import { fetchRuntimeMetrics } from '@/api/health'

const metrics = ref<RuntimeMetrics | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
let controller: AbortController | undefined

function formatBytes(value?: number): string {
  if (value === undefined) return '不可用'
  if (value < 1024) return `${value} B`
  const units = ['KiB', 'MiB', 'GiB', 'TiB']
  let amount = value
  let unit = 'B'
  for (const next of units) {
    amount /= 1024
    unit = next
    if (amount < 1024) break
  }
  return `${amount.toFixed(1)} ${unit}`
}

async function refresh(): Promise<void> {
  controller?.abort()
  controller = new AbortController()
  loading.value = true
  errorMessage.value = null
  try {
    metrics.value = await fetchRuntimeMetrics(controller.signal)
  } catch (cause) {
    if (!controller.signal.aborted) {
      errorMessage.value = cause instanceof Error ? cause.message : '平台运行指标加载失败'
    }
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
onUnmounted(() => controller?.abort())
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
      <section class="content-card" aria-labelledby="runtime-tasks-title">
        <h2 id="runtime-tasks-title">任务</h2>
        <dl class="mt-[16px] grid gap-[8px] text-sm">
          <div class="flex justify-between">
            <dt>排队中</dt>
            <dd>{{ metrics.tasks.queued ?? 0 }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>运行中</dt>
            <dd>{{ metrics.tasks.running ?? 0 }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>失败</dt>
            <dd>{{ metrics.tasks.failed ?? 0 }}</dd>
          </div>
        </dl>
      </section>
      <section class="content-card" aria-labelledby="runtime-models-title">
        <h2 id="runtime-models-title">模型端点</h2>
        <dl class="mt-[16px] grid gap-[8px] text-sm">
          <div class="flex justify-between">
            <dt>正常</dt>
            <dd>{{ metrics.models.healthy }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>异常</dt>
            <dd>{{ metrics.models.unhealthy }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>未知</dt>
            <dd>{{ metrics.models.unknown }}</dd>
          </div>
        </dl>
      </section>
      <section class="content-card" aria-labelledby="runtime-storage-title">
        <h2 id="runtime-storage-title">文件存储</h2>
        <dl class="mt-[16px] grid gap-[8px] text-sm">
          <div class="flex justify-between">
            <dt>已使用</dt>
            <dd>{{ formatBytes(metrics.storage.used_bytes) }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>可用</dt>
            <dd>{{ formatBytes(metrics.storage.free_bytes) }}</dd>
          </div>
          <div class="flex justify-between">
            <dt>总量</dt>
            <dd>{{ formatBytes(metrics.storage.total_bytes) }}</dd>
          </div>
        </dl>
      </section>
    </div>
  </section>
</template>
