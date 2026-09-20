<!-- 公司 API Key 汇总表只展示脱敏前缀、状态和累计用量。 -->
<script setup lang="ts">
import type { ApiKeyTableProps } from './type'
import type { CompanyApiKey } from '@/api/apiKeys'
import { Ban, History, KeyRound } from '@/components'
import { apiKeyStatusLabel, formatApiKeyDate } from './index'
import './index.scss'

defineProps<ApiKeyTableProps>()
const emit = defineEmits<{
  usage: [apiKey: CompanyApiKey]
  revoke: [apiKey: CompanyApiKey]
}>()
</script>

<template>
  <section class="content-card api-key-table-card">
    <header class="api-key-card-header">
      <div><strong>公司下发的 API Key</strong><small>客户只能使用公司下发的 Bearer Key，不能自行创建或管理。</small></div><span>共 {{ items.length }} 个</span>
    </header>
    <div class="api-key-table-wrap">
      <table class="api-key-summary-table">
        <colgroup>
          <col class="api-key-col-client">
          <col class="api-key-col-key">
          <col class="api-key-col-status">
          <col class="api-key-col-quota">
          <col class="api-key-col-usage">
          <col class="api-key-col-last-used">
          <col class="api-key-col-actions">
        </colgroup>
        <thead><tr><th>客户 / 名称</th><th>API Key</th><th>状态</th><th>额度（总 / 已用 / 剩余）</th><th>输入 / 输出</th><th>最后使用</th><th>操作</th></tr></thead><tbody>
          <tr v-if="loading">
            <td colspan="7" class="api-key-empty">
              正在加载 API Key…
            </td>
          </tr>
          <tr v-else-if="!items.length">
            <td colspan="7" class="api-key-empty">
              还没有发放 API Key
            </td>
          </tr>
          <tr v-for="item in items" v-else :key="item.id">
            <td data-label="客户 / 名称">
              <strong>{{ item.tenant_name }}</strong><small>{{ item.name }}</small>
            </td>
            <td data-label="API Key">
              <span class="api-key-prefix-content">
                <KeyRound :size="13" />{{ item.key_prefix }}
              </span>
            </td>
            <td data-label="状态">
              <span class="api-key-status" :class="item.status">{{ apiKeyStatusLabel[item.status] }}</span>
            </td>
            <td class="api-key-numeric" data-label="额度（总 / 已用 / 剩余）">
              <strong>{{ item.token_limit.toLocaleString() }}</strong><small>{{ item.token_used.toLocaleString() }} / {{ item.token_remaining.toLocaleString() }}</small>
            </td>
            <td class="api-key-numeric" data-label="输入 / 输出">
              <strong>{{ item.prompt_tokens.toLocaleString() }}</strong><small>{{ item.completion_tokens.toLocaleString() }}</small>
            </td>
            <td class="api-key-last-used" data-label="最后使用">
              {{ formatApiKeyDate(item.last_used_at) }}
            </td>
            <td class="api-key-action-cell" data-label="操作">
              <div class="api-key-action-list">
                <button type="button" title="查看用量" @click="emit('usage', item)">
                  <History :size="13" />用量
                </button><button type="button" title="撤销 Key" :disabled="item.status !== 'active' || busyId === item.id" @click="emit('revoke', item)">
                  <Ban :size="13" />撤销
                </button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
