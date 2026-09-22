<!-- API Key 请求流水同时展示总账和嵌入、生成模型的分项 Token。 -->
<script setup lang="ts">
import type { ApiKeyUsagePanelProps } from './type'
import type { AppTableColumn } from '@/components'
import { AppTable } from '@/components'
import { useApiKeyUsagePanel } from './index'

defineProps<ApiKeyUsagePanelProps>()
const { sourceLabel } = useApiKeyUsagePanel()
const columns: AppTableColumn<import('@/api/apiKeys').ApiKeyUsageRow>[] = [
  { key: 'time', title: '时间' },
  { key: 'models', title: '模型分项' },
  { key: 'prompt', title: '输入' },
  { key: 'completion', title: '输出' },
  { key: 'total', title: '合计' },
  { key: 'source', title: '来源' },
  { key: 'status', title: '状态' },
]
</script>

<template>
  <section v-if="apiKey" class="content-card mt-[12px] overflow-hidden p-0">
    <header
      class="flex min-h-[58px] items-center justify-between gap-[16px] border-b border-border px-[16px] py-[10px]"
    >
      <div>
        <strong class="block text-[13px] font-semibold">{{ apiKey.name }} · Token 用量</strong>
        <small class="mt-[2px] block text-[10px] text-muted-foreground"
          >输入包含检索嵌入和生成输入，输出为生成模型输出；额度按合计扣减。</small
        >
      </div>
      <span class="text-[11px] text-muted-foreground"
        >最近 {{ Math.min(items.length, recentLimit) }} 条 / 共
        {{ summary?.request_count ?? 0 }} 条</span
      >
    </header>
    <div class="grid grid-cols-3 border-b border-border max-sm:grid-cols-1">
      <div class="border-r border-border px-[16px] py-[14px] max-sm:border-r-0 max-sm:border-b">
        <small class="block text-[10px] text-muted-foreground">累计输入 Token</small>
        <strong class="mt-[4px] block text-lg">{{
          (summary?.prompt_tokens ?? 0).toLocaleString()
        }}</strong>
      </div>
      <div class="border-r border-border px-[16px] py-[14px] max-sm:border-r-0 max-sm:border-b">
        <small class="block text-[10px] text-muted-foreground">累计输出 Token</small>
        <strong class="mt-[4px] block text-lg">{{
          (summary?.completion_tokens ?? 0).toLocaleString()
        }}</strong>
      </div>
      <div class="px-[16px] py-[14px]">
        <small class="block text-[10px] text-muted-foreground">累计合计 Token</small>
        <strong class="mt-[4px] block text-lg">{{
          (summary?.total_tokens ?? 0).toLocaleString()
        }}</strong>
      </div>
    </div>
    <div class="overflow-x-auto">
      <AppTable
        :rows="items"
        :columns="columns"
        row-key="request_id"
        :loading="loading"
        loading-text="正在加载用量…"
        empty-text="暂时没有用量流水"
        class="w-full min-w-[760px] text-left"
      >
        <template #cell-time="{ row: item }">
          {{ new Date(item.created_at).toLocaleString() }}
        </template>
        <template #cell-models="{ row: item }">
          <span v-if="item.model_usage.embedding"
            >嵌入 {{ item.model_usage.embedding.total_tokens.toLocaleString() }}</span
          ><span v-if="item.model_usage.generation"
            >生成 {{ item.model_usage.generation.total_tokens.toLocaleString() }}</span
          ><small class="mt-[2px] block text-[10px] text-muted-foreground">{{
            item.model_name
          }}</small>
        </template>
        <template #cell-prompt="{ row: item }">
          {{ item.prompt_tokens.toLocaleString() }}
        </template>
        <template #cell-completion="{ row: item }">
          {{ item.completion_tokens.toLocaleString() }}
        </template>
        <template #cell-total="{ row: item }">
          <strong>{{ item.total_tokens.toLocaleString() }}</strong>
        </template>
        <template #cell-source="{ row: item }">
          {{ sourceLabel(item.usage_source) }}
        </template>
        <template #cell-status="{ row: item }">
          {{ item.status === 'completed' ? '完成' : item.status === 'cancelled' ? '取消' : '失败' }}
        </template>
      </AppTable>
    </div>
  </section>
</template>
