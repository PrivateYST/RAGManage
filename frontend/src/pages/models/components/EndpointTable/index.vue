<script setup lang="ts">
import type { ModelEndpoint } from '../../../../api/models'
import type { EndpointTableProps } from './type'
import { Activity, Pencil, Power } from 'lucide-vue-next'
import { endpointTypeLabel } from '../../enum'
import { useEndpointTable } from './index'
import './index.scss'

defineProps<EndpointTableProps>()
const emit = defineEmits<{
  edit: [endpoint: ModelEndpoint]
  toggle: [endpoint: ModelEndpoint]
  check: [endpoint: ModelEndpoint, modelName: string]
}>()
const { selectedModel, setSelectedModel } = useEndpointTable()
</script>

<template>
  <section class="content-card endpoint-card">
    <header class="endpoint-card-header">
      <div><strong>模型端点</strong><small>密钥由环境变量注入，页面和数据库均不保存明文。</small></div>
      <span>共 {{ items.length }} 个</span>
    </header>
    <div class="endpoint-table-wrap">
      <table>
        <thead><tr><th>端点</th><th>用途</th><th>模型白名单</th><th>健康状态</th><th>状态</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="6" class="endpoint-empty">
              正在加载模型端点…
            </td>
          </tr>
          <tr v-else-if="!items.length">
            <td colspan="6" class="endpoint-empty">
              尚未登记模型端点
            </td>
          </tr>
          <template v-else>
            <tr v-for="endpoint in items" :key="endpoint.id">
              <td><strong>{{ endpoint.name }}</strong><small>{{ endpoint.base_url }}</small></td>
              <td>{{ endpointTypeLabel[endpoint.endpoint_type] }}</td>
              <td>
                <select
                  class="model-select"
                  :value="selectedModel(endpoint)"
                  :aria-label="`${endpoint.name} 检查模型`"
                  @change="setSelectedModel(endpoint.id, ($event.target as HTMLSelectElement).value)"
                >
                  <option v-for="model in endpoint.allowed_models" :key="model" :value="model">
                    {{ model }}
                  </option>
                </select>
              </td>
              <td>
                <span class="health-state" :class="endpoint.health_status">{{ endpoint.health_status === 'healthy' ? '健康' : endpoint.health_status === 'unhealthy' ? '异常' : '未检查' }}</span>
                <small v-if="endpoint.last_latency_ms !== null">{{ endpoint.last_latency_ms }} ms<span v-if="endpoint.observed_dimension"> · {{ endpoint.observed_dimension }} 维</span></small>
              </td>
              <td><span class="status-pill" :class="endpoint.status">{{ endpoint.status === 'active' ? '已启用' : '已停用' }}</span></td>
              <td class="endpoint-actions">
                <button type="button" :disabled="endpoint.status !== 'active' || busyId === `health-${endpoint.id}`" @click="emit('check', endpoint, selectedModel(endpoint))">
                  <Activity :size="13" />实测
                </button>
                <button type="button" @click="emit('edit', endpoint)">
                  <Pencil :size="13" />编辑
                </button>
                <button type="button" :disabled="busyId === `endpoint-${endpoint.id}`" @click="emit('toggle', endpoint)">
                  <Power :size="13" />{{ endpoint.status === 'active' ? '停用' : '启用' }}
                </button>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>
