<!-- 服务状态卡片：负责查询基础依赖健康状态，并把失败反馈交给全局 Toast。 -->
<script setup lang="ts">
import type { Health } from '@/api/health'
import { onMounted, onUnmounted, shallowRef } from 'vue'
import { fetchHealth } from '@/api/health'
import { useAppToast } from '@/composables/useToast'

const health = shallowRef<Health | null>(null)
const toast = useAppToast()
const loading = shallowRef(false)
let controller: AbortController | undefined
const labels: Record<string, string> = {
  database: 'PostgreSQL / pgvector',
  redis: 'Redis',
  storage: '文件存储',
}
const statuses: Record<string, string> = {
  ok: '正常',
  unavailable: '无法连接',
  unconfigured: '待配置',
  vector_unavailable: '扩展未就绪',
}

async function refresh() {
  controller?.abort()
  const current = new AbortController()
  controller = current
  loading.value = true
  health.value = null
  const timeout = setTimeout(() => current.abort(), 10000)
  try {
    health.value = await fetchHealth(current.signal)
  } catch {
    toast.error('服务状态检查失败', '请检查后端服务是否启动后重试。')
  } finally {
    clearTimeout(timeout)
    loading.value = false
  }
}
onMounted(refresh)
onUnmounted(() => controller?.abort())
</script>

<template>
  <section class="content-card mt-[24px]" :aria-busy="loading">
    <div
      class="mb-[20px] flex items-center justify-between gap-[16px] border-b border-border pb-[16px]"
    >
      <div>
        <p class="eyebrow mb-[4px]">基础设施</p>
        <h2>服务状态</h2>
      </div>
      <button class="secondary-button" type="button" :disabled="loading" @click="refresh">
        {{ loading ? '检查中…' : '重新检查' }}
      </button>
    </div>
    <p v-if="loading" class="text-xs text-muted-foreground" role="status">正在连接本地服务…</p>
    <template v-else-if="health">
      <p
        class="mb-[16px] rounded-md border px-[12px] py-[8px] text-xs"
        :class="
          health.status === 'ready'
            ? 'border-status-up/20 bg-status-up-soft text-status-up'
            : 'border-status-warning/20 bg-status-warning-soft text-status-warning'
        "
        role="status"
      >
        {{ health.status === 'ready' ? '基础服务已就绪' : '部分服务尚未就绪' }}
      </p>
      <dl class="grid gap-[8px] sm:grid-cols-2">
        <div
          v-for="(status, name) in health.checks"
          :key="name"
          class="flex items-center justify-between gap-[16px] rounded-md border border-border bg-background px-[12px] py-[8px]"
        >
          <dt class="text-xs text-foreground">
            {{ labels[name] ?? name }}
          </dt>
          <dd
            class="text-xs font-medium"
            :class="status === 'ok' ? 'text-status-up' : 'text-muted-foreground'"
          >
            {{ statuses[status] ?? '待检查' }}
          </dd>
        </div>
      </dl>
    </template>
    <p v-else class="text-xs text-muted-foreground" role="status">暂无服务状态数据，请重新检查。</p>
  </section>
</template>
