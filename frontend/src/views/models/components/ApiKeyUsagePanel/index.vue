<!-- API Key 请求流水同时展示总账和嵌入、生成模型的分项 Token。 -->
<script setup lang="ts">
import type { ApiKeyUsagePanelProps } from './type'
import { useApiKeyUsagePanel } from './index'
import './index.scss'

defineProps<ApiKeyUsagePanelProps>()
const { sourceLabel } = useApiKeyUsagePanel()
</script>

<template>
  <section v-if="apiKey" class="content-card api-key-usage-card">
    <header class="api-key-card-header">
      <div><strong>{{ apiKey.name }} · Token 用量</strong><small>输入包含检索嵌入和生成输入，输出为生成模型输出；额度按合计扣减。</small></div><span>最近 {{ Math.min(items.length, recentLimit) }} 条 / 共 {{ summary?.request_count ?? 0 }} 条</span>
    </header>
    <div class="api-key-usage-summary">
      <div><small>累计输入 Token</small><strong>{{ (summary?.prompt_tokens ?? 0).toLocaleString() }}</strong></div><div><small>累计输出 Token</small><strong>{{ (summary?.completion_tokens ?? 0).toLocaleString() }}</strong></div><div><small>累计合计 Token</small><strong>{{ (summary?.total_tokens ?? 0).toLocaleString() }}</strong></div>
    </div>
    <div class="api-key-table-wrap">
      <table>
        <thead><tr><th>时间</th><th>模型分项</th><th>输入</th><th>输出</th><th>合计</th><th>来源</th><th>状态</th></tr></thead><tbody>
          <tr v-if="loading">
            <td colspan="7" class="api-key-empty">
              正在加载用量…
            </td>
          </tr><tr v-else-if="!items.length">
            <td colspan="7" class="api-key-empty">
              暂时没有用量流水
            </td>
          </tr><tr v-for="item in items" v-else :key="item.request_id">
            <td>{{ new Date(item.created_at).toLocaleString() }}</td><td><span v-if="item.model_usage.embedding">嵌入 {{ item.model_usage.embedding.total_tokens.toLocaleString() }}</span><span v-if="item.model_usage.generation">生成 {{ item.model_usage.generation.total_tokens.toLocaleString() }}</span><small>{{ item.model_name }}</small></td><td>{{ item.prompt_tokens.toLocaleString() }}</td><td>{{ item.completion_tokens.toLocaleString() }}</td><td><strong>{{ item.total_tokens.toLocaleString() }}</strong></td><td>{{ sourceLabel(item.usage_source) }}</td><td>{{ item.status === 'completed' ? '完成' : item.status === 'cancelled' ? '取消' : '失败' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
