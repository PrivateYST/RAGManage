<!-- 客户空间管理：组合空间表格、空间创建和医院 API Key 操作子视图。 -->
<script setup lang="ts">
import type { TenantRow } from '@/api/admin'
import type { AppTableColumn } from '@/components'
import { onMounted } from 'vue'
import { AppTable, Copy, KeyRound, Plus } from '@/components'
import ApiKeyCreateDialog from '@/views/models/components/ApiKeyCreateDialog/index.vue'
import ApiKeyRevealDialog from '@/views/models/components/ApiKeyRevealDialog/index.vue'
import CreateSpaceDialog from './components/CreateSpaceDialog/index.vue'
import TenantApiKeyDialog from './components/TenantApiKeyDialog/index.vue'
import { useSpacesPage } from './index'

const {
  tenants,
  canCreateSpace,
  isPlatformAdmin,
  loading,
  loadError,
  showCreateDialog,
  savingTenant,
  selectedTenantForKey,
  tenantKeyDialogOpen,
  tenantKeySubmitting,
  revealedTenantKey,
  loadTenants,
  createSpace,
  openKeyDialog,
  saveTenantKey,
  finishTenantKeyConfiguration,
  copyTenantKey,
  closeKeyReveal,
  toast,
} = useSpacesPage()

const columns: AppTableColumn<TenantRow>[] = [
  { key: 'name', title: '空间名称' },
  { key: 'code', title: '空间编码', field: 'code' },
  { key: 'members', title: '成员数', field: 'member_count' },
  { key: 'knowledgeBases', title: '知识库数', field: 'knowledge_base_count' },
  { key: 'apiKey', title: '客户 API Key' },
  { key: 'status', title: '状态' },
  { key: 'created', title: '创建时间' },
  { key: 'actions', title: '操作' },
]

/** 生命周期标签只反映服务端状态；不存在的 Key 明确显示为未配置。 */
function keyStatusLabel(status: TenantRow['api_key_status']): string {
  if (status === 'active') return '已启用'
  if (status === 'disabled') return '已停用'
  if (status === 'expired') return '已过期'
  if (status === 'revoked') return '已撤销'
  return '未配置'
}

/** Key 状态使用通用语义色，只有当前可用状态呈现成功色。 */
function keyStatusClass(status: TenantRow['api_key_status']): string {
  return status === 'active' ? 'published' : status ? 'disabled' : ''
}

/** 创建成功才关闭表单，失败时保留已填内容供修正。 */
async function handleCreate(form: { code: string; name: string }): Promise<void> {
  if (await createSpace(form)) showCreateDialog.value = false
}

onMounted(() => void loadTenants())
</script>

<template>
  <section class="page-section">
    <div class="page-intro">
      <div>
        <p class="eyebrow">平台管理</p>
        <h1>空间管理</h1>
        <p class="page-description">创建客户空间并查看成员与知识库使用情况。</p>
      </div>
      <button v-if="canCreateSpace" class="primary-button" type="button" @click="showCreateDialog = true">
        <Plus :size="16" />新建空间
      </button>
    </div>
    <div v-if="loading" class="content-card module-placeholder" role="status">
      <span class="loading-spinner" />
      <p>正在加载空间…</p>
    </div>
    <div
      v-else-if="loadError"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px]"
      role="alert"
    >
      <strong class="text-sm text-destructive">空间列表加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ loadError }}</p>
      <button class="secondary-button" type="button" @click="loadTenants">重新加载</button>
    </div>
    <div v-else class="content-card table-card">
      <div class="table-toolbar">
        <span class="table-count">共 {{ tenants.length }} 个客户空间</span>
      </div>
      <AppTable :rows="tenants" :columns="columns" row-key="id">
        <template #cell-name="{ row }"
          ><strong>{{ row.name }}</strong></template
        >
        <template #cell-code="{ row }"
          ><code>{{ row.code }}</code></template
        >
        <template #cell-status="{ row }"
          ><span class="status-pill" :class="row.status === 'active' ? 'published' : 'disabled'">{{
            row.status === 'active' ? '启用' : '停用'
          }}</span></template
        >
        <template #cell-apiKey="{ row }">
          <div class="flex min-w-[170px] flex-col gap-[3px]">
            <span class="status-pill w-fit" :class="keyStatusClass(row.api_key_status)">{{
              keyStatusLabel(row.api_key_status)
            }}</span>
            <code v-if="row.api_key_prefix">{{ row.api_key_prefix }}</code>
            <small v-if="row.api_key_id"
              >已用 {{ (row.api_key_token_used ?? 0).toLocaleString() }} / 剩余
              {{ (row.api_key_token_remaining ?? 0).toLocaleString() }} Token</small
            >
            <small v-if="row.api_key_id" class="text-muted-foreground">
              {{ row.api_key_configured_at ? '医院已确认配置' : '待医院粘贴确认' }}
            </small>
          </div>
        </template>
        <template #cell-created="{ row }">{{
          new Date(row.created_at).toLocaleDateString('zh-CN')
        }}</template>
        <template #cell-actions="{ row }">
          <button
            v-if="!isPlatformAdmin && row.api_key_id && row.status === 'active'"
            class="table-action inline-flex items-center gap-[4px]"
            type="button"
            @click="openKeyDialog(row)"
          >
            <KeyRound :size="13" />填写 Key
          </button>
          <button
            v-else-if="isPlatformAdmin && !row.api_key_id && row.status === 'active'"
            class="table-action inline-flex items-center gap-[4px]"
            type="button"
            @click="openKeyDialog(row)"
          >
            <KeyRound :size="13" />配置 Key
          </button>
          <button
            v-else-if="isPlatformAdmin && row.api_key_id"
            class="table-action inline-flex items-center gap-[4px]"
            type="button"
            @click="copyTenantKey(row)"
          >
            <Copy :size="13" />复制完整 Key
          </button>
          <span v-else class="text-[11px] text-muted-foreground">空间已停用</span>
        </template>
      </AppTable>
    </div>
  </section>
  <CreateSpaceDialog
    :open="showCreateDialog"
    :saving="savingTenant"
    @close="showCreateDialog = false"
    @submit="handleCreate"
  />
  <ApiKeyCreateDialog
    v-if="isPlatformAdmin"
    :open="tenantKeyDialogOpen"
    :tenants="selectedTenantForKey ? [selectedTenantForKey] : []"
    :submitting="tenantKeySubmitting"
    @close="tenantKeyDialogOpen = false"
    @submit="saveTenantKey"
  />
  <TenantApiKeyDialog
    v-if="!isPlatformAdmin && selectedTenantForKey"
    :open="tenantKeyDialogOpen"
    :tenant-id="selectedTenantForKey.id"
    :tenant-name="selectedTenantForKey.name"
    @close="tenantKeyDialogOpen = false"
    @configured="finishTenantKeyConfiguration"
  />
  <ApiKeyRevealDialog
    :api-key="revealedTenantKey"
    @close="closeKeyReveal"
    @copied="toast.success('客户 API Key 已复制')"
  />
</template>

<style scoped lang="scss" src="./index.scss"></style>
