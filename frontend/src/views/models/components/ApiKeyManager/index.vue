<!-- 公司 API Key 管理工作区：组合创建、列表和 Token 用量三个职责明确的子组件。 -->
<script setup lang="ts">
import { Plus, RefreshCw } from '@/components'
import ApiKeyCreateDialog from '../ApiKeyCreateDialog/index.vue'
import ApiKeyRevealDialog from '../ApiKeyRevealDialog/index.vue'
import ApiKeyTable from '../ApiKeyTable/index.vue'
import ApiKeyUsagePanel from '../ApiKeyUsagePanel/index.vue'
import { useApiKeyManager } from './index'
import './index.scss'

const {
  items,
  tenants,
  selected,
  usage,
  usageSummary,
  usageRecentLimit,
  loading,
  usageLoading,
  submitting,
  busyId,
  error,
  success,
  createOpen,
  revealedKey,
  pendingRevoke,
  load,
  openCreate,
  submit,
  requestRevoke,
  cancelRevoke,
  confirmRevoke,
  showUsage,
  copyRevealedKey,
  closeRevealedKey,
} = useApiKeyManager()
</script>

<template>
  <section class="api-key-manager">
    <div class="api-key-manager-actions">
      <div><strong>客户 API 凭据</strong><small>Token 额度用尽、到期或撤销后，Key 会立即停止鉴权。</small></div>
      <div>
        <button class="secondary-button" type="button" :disabled="loading" @click="load">
          <RefreshCw :size="14" />刷新
        </button><button class="primary-button" type="button" @click="openCreate">
          <Plus :size="14" />发放 API Key
        </button>
      </div>
    </div>
    <div v-if="error" class="error-banner" role="alert">
      {{ error }}
    </div>
    <div v-if="success" class="model-success" role="status">
      {{ success }}
    </div>
    <div v-if="pendingRevoke" class="api-key-revoke-prompt" role="alert">
      <span>确认撤销“{{ pendingRevoke.name }}”？客户将立即无法继续调用。</span>
      <div>
        <button type="button" class="secondary-button" @click="cancelRevoke">
          取消
        </button><button type="button" class="destructive-button" :disabled="busyId === pendingRevoke.id" @click="confirmRevoke">
          确认撤销
        </button>
      </div>
    </div>
    <ApiKeyTable :items="items" :loading="loading" :busy-id="busyId" @usage="showUsage" @revoke="requestRevoke" />
    <ApiKeyUsagePanel
      :api-key="selected"
      :items="usage"
      :summary="usageSummary"
      :recent-limit="usageRecentLimit"
      :loading="usageLoading"
    />
    <ApiKeyCreateDialog :open="createOpen" :tenants="tenants" :submitting="submitting" @close="createOpen = false" @submit="submit" />
    <ApiKeyRevealDialog :api-key="revealedKey" @close="closeRevealedKey" @copied="copyRevealedKey" />
  </section>
</template>
