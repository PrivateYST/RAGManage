<!-- 基础服务状态卡片：只呈现页面传入的快照，并把刷新意图上报给页面。 -->
<script setup lang="ts">
import type { EnvironmentStatusEmits, EnvironmentStatusProps } from './type'
import { getEnvironmentCheckLabel, getEnvironmentStatusLabel } from './index'
import './index.scss'

defineProps<EnvironmentStatusProps>()
const emit = defineEmits<EnvironmentStatusEmits>()
</script>

<template>
  <section
    class="content-card mt-[24px]"
    :aria-busy="loading"
    aria-labelledby="environment-status-title"
  >
    <div
      class="mb-[20px] flex items-center justify-between gap-[16px] border-b border-border pb-[16px]"
    >
      <div>
        <p class="eyebrow mb-[4px]">基础设施</p>
        <h2 id="environment-status-title">服务状态</h2>
      </div>
      <button class="secondary-button" type="button" :disabled="loading" @click="emit('refresh')">
        {{ loading ? '检查中…' : '重新检查' }}
      </button>
    </div>
    <p v-if="loading" class="text-xs text-muted-foreground" role="status">正在连接本地服务…</p>
    <p
      v-else-if="errorMessage"
      class="rounded-md border border-status-danger/20 bg-status-danger-soft px-[12px] py-[8px] text-xs text-status-danger"
      role="alert"
    >
      {{ errorMessage }}
    </p>
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
          <dt class="text-xs text-foreground">{{ getEnvironmentCheckLabel(name) }}</dt>
          <dd
            class="text-xs font-medium"
            :class="status === 'ok' ? 'text-status-up' : 'text-muted-foreground'"
          >
            {{ getEnvironmentStatusLabel(status) }}
          </dd>
        </div>
      </dl>
    </template>
    <p v-else class="text-xs text-muted-foreground" role="status">暂无服务状态数据，请重新检查。</p>
  </section>
</template>
