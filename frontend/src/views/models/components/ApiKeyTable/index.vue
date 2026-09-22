<!-- 公司 API Key 汇总表只展示脱敏前缀、状态和累计用量。 -->
<script setup lang="ts">
import type { ApiKeyTableProps } from './type'
import type { CompanyApiKey } from '@/api/apiKeys'
import type { AppTableColumn } from '@/components'
import { AppTable, Copy, History, KeyRound, Power, Trash2 } from '@/components'
import { apiKeyStatusLabel, formatApiKeyDate } from './index'
import './index.scss'

defineProps<ApiKeyTableProps>()
const emit = defineEmits<{
  usage: [apiKey: CompanyApiKey]
  delete: [apiKey: CompanyApiKey]
  toggleStatus: [apiKey: CompanyApiKey]
  copy: [apiKey: CompanyApiKey]
}>()
function statusText(status: CompanyApiKey['status']): string {
  return apiKeyStatusLabel[status]
}
const columns: AppTableColumn<CompanyApiKey>[] = [
  { key: 'client', title: '客户 / 名称' },
  { key: 'key', title: 'API Key' },
  { key: 'status', title: '状态' },
  { key: 'quota', title: '额度（总 / 已用 / 剩余）' },
  { key: 'usage', title: '输入 / 输出' },
  { key: 'lastUsed', title: '最后使用' },
  { key: 'actions', title: '操作' },
]
</script>

<template>
  <section class="content-card overflow-hidden p-0">
    <header
      class="flex min-h-[58px] items-center justify-between gap-[16px] border-b border-border px-[16px] py-[10px]"
    >
      <div>
        <strong class="block text-[13px] font-semibold">医院 Open WebUI API Key</strong>
        <small class="mt-[2px] block text-[10px] text-muted-foreground"
          >每家医院共用一把原生 `sk-` Key；员工无需注册 Open WebUI 用户。</small
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
        empty-text="还没有发放 API Key"
        class="w-full min-w-[980px] text-left"
      >
        <template #cell-client="{ row: item }">
          <strong class="block text-xs font-semibold text-foreground">{{
            item.tenant_name
          }}</strong>
          <small class="mt-[2px] block text-[10px] text-muted-foreground">{{ item.name }}</small>
        </template>
        <template #cell-key="{ row: item }">
          <div class="api-key-prefix-content">
            <span
              class="flex max-w-full items-center gap-[6px] overflow-hidden font-mono text-[10px] text-muted-foreground"
            >
              <KeyRound :size="13" />{{ item.key_prefix }}
            </span>
            <small class="mt-[4px] block text-[10px] text-muted-foreground">
              {{ item.provider === 'open_webui' ? 'Open WebUI 原生 Key' : '本地兼容 Key' }}
            </small>
            <button
              class="mt-[6px] inline-flex items-center gap-[4px] border-0 bg-transparent p-0 text-[10px] text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              type="button"
              title="查询并复制完整 API Key"
              @click="emit('copy', item)"
            >
              <Copy :size="12" />复制完整 Key
            </button>
          </div>
        </template>
        <template #cell-status="{ row: item }">
          <button
            v-if="item.status === 'active' || item.status === 'disabled'"
            class="inline-flex min-h-[20px] items-center gap-[4px] rounded-full border-0 px-[8px] text-[10px] font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            :class="item.status"
            type="button"
            :disabled="busyId === item.id"
            :title="item.status === 'active' ? '点击停用此 Key' : '点击启用此 Key'"
            @click="emit('toggleStatus', item)"
          >
            <Power :size="11" />{{ statusText(item.status) }}
          </button>
          <span
            v-else
            class="inline-flex min-h-[20px] items-center rounded-full px-[8px] text-[10px] font-medium"
            :class="item.status"
            >{{ statusText(item.status) }}</span
          >
        </template>
        <template #cell-quota="{ row: item }">
          <strong class="block text-xs font-semibold text-foreground">{{
            item.token_limit.toLocaleString()
          }}</strong>
          <small class="mt-[2px] block text-[10px] text-muted-foreground"
            >{{ item.token_used.toLocaleString() }} /
            {{ item.token_remaining.toLocaleString() }}</small
          >
        </template>
        <template #cell-usage="{ row: item }">
          <strong class="block text-xs font-semibold text-foreground">{{
            item.prompt_tokens.toLocaleString()
          }}</strong>
          <small class="mt-[2px] block text-[10px] text-muted-foreground">{{
            item.completion_tokens.toLocaleString()
          }}</small>
        </template>
        <template #cell-lastUsed="{ row: item }">
          {{ formatApiKeyDate(item.last_used_at) }}
        </template>
        <template #cell-actions="{ row: item }">
          <div class="api-key-action-list flex flex-nowrap items-center gap-[6px]">
            <button
              class="inline-flex h-[28px] shrink-0 items-center gap-[4px] rounded-md border border-border bg-background px-[8px] text-[11px] text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              type="button"
              title="查看用量"
              @click="emit('usage', item)"
            >
              <History :size="13" />用量</button
            ><button
              class="inline-flex h-[28px] shrink-0 items-center gap-[4px] rounded-md border border-border bg-background px-[8px] text-[11px] text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50"
              type="button"
              title="删除 Key"
              :disabled="busyId === item.id"
              @click="emit('delete', item)"
            >
              <Trash2 :size="13" />删除
            </button>
          </div>
        </template>
      </AppTable>
    </div>
  </section>
</template>
