<script setup lang="ts">
import type { EndpointTableProps } from './type'
import type { ModelEndpoint } from '@/api/models'
import type { AppTableColumn } from '@/components'
import { Activity, AppTable, Pencil, Power } from '@/components'
import { endpointTypeLabel } from '@/views/models/enum'
import { useEndpointTable } from './index'

defineProps<EndpointTableProps>()
const emit = defineEmits<{
  edit: [endpoint: ModelEndpoint]
  toggle: [endpoint: ModelEndpoint]
  check: [endpoint: ModelEndpoint, modelName: string]
}>()
const { selectedModel, setSelectedModel } = useEndpointTable()
function endpointPurpose(endpoint: ModelEndpoint): string {
  return endpointTypeLabel[endpoint.endpoint_type]
}
const columns: AppTableColumn<ModelEndpoint>[] = [
  { key: 'endpoint', title: '端点' },
  { key: 'purpose', title: '用途' },
  { key: 'models', title: '模型白名单' },
  { key: 'health', title: '健康状态' },
  { key: 'status', title: '状态' },
  { key: 'actions', title: '操作' },
]
</script>

<template>
  <section class="content-card overflow-hidden p-0">
    <header
      class="flex min-h-[62px] items-center justify-between gap-[16px] border-b border-border px-[18px] py-[12px]"
    >
      <div>
        <strong class="block text-[13px] font-semibold">模型端点</strong>
        <small class="mt-[2px] block text-[11px] text-muted-foreground"
          >密钥由环境变量注入，页面和数据库均不保存明文。</small
        >
      </div>
      <span class="text-[11px] text-muted-foreground">共 {{ items.length }} 个</span>
    </header>
    <div class="overflow-x-auto">
      <AppTable
        :rows="items"
        :columns="columns"
        row-key="id"
        :loading="loading"
        empty-text="尚未登记模型端点"
        class="w-full min-w-[980px] text-left"
      >
        <template #cell-endpoint="{ row: endpoint }">
          <strong class="block text-[13px] font-semibold text-foreground">{{
            endpoint.name
          }}</strong>
          <small class="mt-[2px] block max-w-[280px] truncate text-[11px] text-muted-foreground">{{
            endpoint.base_url
          }}</small>
        </template>
        <template #cell-purpose="{ row: endpoint }">
          {{ endpointPurpose(endpoint) }}
        </template>
        <template #cell-models="{ row: endpoint }">
          <select
            class="h-[32px] w-[190px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            :value="selectedModel(endpoint)"
            :aria-label="`${endpoint.name} 检查模型`"
            @change="setSelectedModel(endpoint.id, ($event.target as HTMLSelectElement).value)"
          >
            <option v-for="model in endpoint.allowed_models" :key="model" :value="model">
              {{ model }}
            </option>
          </select>
        </template>
        <template #cell-health="{ row: endpoint }">
          <span
            class="inline-flex rounded px-[8px] py-[2px] text-[10px]"
            :class="
              endpoint.health_status === 'healthy'
                ? 'bg-status-up-soft text-status-up'
                : endpoint.health_status === 'unhealthy'
                  ? 'bg-destructive/10 text-destructive'
                  : 'bg-secondary text-muted-foreground'
            "
            >{{
              endpoint.health_status === 'healthy'
                ? '健康'
                : endpoint.health_status === 'unhealthy'
                  ? '异常'
                  : '未检查'
            }}</span
          >
          <small
            v-if="endpoint.last_latency_ms !== null"
            class="mt-[2px] block text-[10px] text-muted-foreground"
            >{{ endpoint.last_latency_ms }} ms<span v-if="endpoint.observed_dimension">
              · {{ endpoint.observed_dimension }} 维</span
            ></small
          >
        </template>
        <template #cell-status="{ row: endpoint }">
          <span
            class="inline-flex min-h-[20px] items-center rounded-full px-[8px] text-[10px] font-medium"
            :class="
              endpoint.status === 'active'
                ? 'bg-status-up-soft text-status-up'
                : 'bg-secondary text-muted-foreground'
            "
            >{{ endpoint.status === 'active' ? '已启用' : '已停用' }}</span
          >
        </template>
        <template #cell-actions="{ row: endpoint }">
          <button
            class="mr-[10px] inline-flex items-center gap-[4px] border-0 bg-transparent px-0 py-[4px] text-[11px] text-muted-foreground hover:text-primary disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            type="button"
            :disabled="endpoint.status !== 'active' || busyId === `health-${endpoint.id}`"
            @click="emit('check', endpoint, selectedModel(endpoint))"
          >
            <Activity :size="13" />实测
          </button>
          <button
            class="mr-[10px] inline-flex items-center gap-[4px] border-0 bg-transparent px-0 py-[4px] text-[11px] text-muted-foreground hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            type="button"
            @click="emit('edit', endpoint)"
          >
            <Pencil :size="13" />编辑
          </button>
          <button
            class="inline-flex items-center gap-[4px] border-0 bg-transparent px-0 py-[4px] text-[11px] text-muted-foreground hover:text-primary disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            type="button"
            :disabled="busyId === `endpoint-${endpoint.id}`"
            @click="emit('toggle', endpoint)"
          >
            <Power :size="13" />{{ endpoint.status === 'active' ? '停用' : '启用' }}
          </button>
        </template>
      </AppTable>
    </div>
  </section>
</template>
