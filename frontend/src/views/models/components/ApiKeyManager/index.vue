<!-- 公司 API Key 管理工作区：组合创建、列表和 Token 用量三个职责明确的子组件。 -->
<script setup lang="ts">
import { AppConfirmDialog, KeyRound, Plus, RefreshCw } from '@/components'
import ApiKeyCreateDialog from '../ApiKeyCreateDialog/index.vue'
import ApiKeyRevealDialog from '../ApiKeyRevealDialog/index.vue'
import ApiKeyTable from '../ApiKeyTable/index.vue'
import ApiKeyUsagePanel from '../ApiKeyUsagePanel/index.vue'
import { useApiKeyManager } from './index'

const emit = defineEmits<{ configure: [] }>()
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
  createOpen,
  revealedKey,
  pendingDelete,
  pendingStatus,
  load,
  openCreate,
  submit,
  requestDelete,
  cancelDelete,
  confirmDelete,
  toggleStatus,
  cancelStatus,
  confirmStatus,
  showUsage,
  copyRevealedKey,
  copyKeyIdentifier,
  closeRevealedKey,
} = useApiKeyManager()
</script>

<template>
  <section class="flex flex-col gap-[12px]">
    <div
      class="flex min-h-[58px] items-center justify-between gap-[16px] rounded-lg border border-border bg-card px-[14px] py-[10px] max-sm:items-stretch max-sm:flex-col"
    >
      <div>
        <strong class="block text-[13px] font-semibold">医院模型网关凭据</strong>
        <small class="mt-[2px] block text-[10px] text-muted-foreground"
          >每家医院一把 Open WebUI 原生 Key；额度用尽、到期、停用或删除后会立即停止调用。</small
        >
      </div>
      <div class="flex gap-[8px] max-sm:justify-end">
        <button class="secondary-button" type="button" @click="emit('configure')">
          <KeyRound :size="14" />配置全局网关 Key
        </button>
        <button class="secondary-button" type="button" :disabled="loading" @click="load">
          <RefreshCw :size="14" />刷新</button
        ><button class="primary-button" type="button" @click="openCreate">
          <Plus :size="14" />生成医院网关 Key
        </button>
      </div>
    </div>
    <ApiKeyTable
      :items="items"
      :loading="loading"
      :busy-id="busyId"
      @usage="showUsage"
      @delete="requestDelete"
      @toggle-status="toggleStatus"
      @copy="copyKeyIdentifier"
    />
    <ApiKeyUsagePanel
      :api-key="selected"
      :items="usage"
      :summary="usageSummary"
      :recent-limit="usageRecentLimit"
      :loading="usageLoading"
    />
    <ApiKeyCreateDialog
      :open="createOpen"
      :tenants="tenants"
      :submitting="submitting"
      @close="createOpen = false"
      @submit="submit"
    />
    <ApiKeyRevealDialog
      :api-key="revealedKey"
      @close="closeRevealedKey"
      @copied="copyRevealedKey"
    />
    <AppConfirmDialog
      :open="Boolean(pendingDelete)"
      :title="pendingDelete ? `确认删除“${pendingDelete.name}”？` : '确认删除 API Key'"
      description="删除后该 Key 将立即失效，但历史用量记录仍会保留。"
      confirm-label="确认删除"
      :busy="Boolean(pendingDelete && busyId === pendingDelete.id)"
      @update:open="(open) => !open && cancelDelete()"
      @confirm="confirmDelete"
    />
    <AppConfirmDialog
      :open="Boolean(pendingStatus)"
      :title="pendingStatus ? `确认停用“${pendingStatus.name}”？` : '确认停用 API Key'"
      description="停用后该 API Key 将立即停止调用；历史用量记录仍会保留。"
      confirm-label="确认停用"
      :busy="Boolean(pendingStatus && busyId === pendingStatus.id)"
      @update:open="(open) => !open && cancelStatus()"
      @confirm="confirmStatus"
    />
  </section>
</template>
