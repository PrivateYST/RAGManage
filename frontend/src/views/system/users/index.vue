<!-- 用户管理页面：组合用户表格、创建/详情子视图和停用确认。 -->
<script setup lang="ts">
import type { TenantRow, UserRow } from '@/api/admin'
import type { AppTableColumn } from '@/components'
import { onMounted, ref, shallowRef } from 'vue'
import { fetchTenants } from '@/api/admin'
import { AppConfirmDialog, Plus } from '@/components'
import { useAppToast } from '@/composables/useToast'
import CreateUserDialog from './components/CreateUserDialog/index.vue'
import EditUserDialog from './components/EditUserDialog/index.vue'
import UserDetailDialog from './components/UserDetailDialog/index.vue'
import { useUserManagementPage } from './index'

const toast = useAppToast()
const tenants = ref<TenantRow[]>([])
const showCreateDialog = ref(false)
const editDialogOpen = ref(false)
const editingUser = shallowRef<UserRow | null>(null)
const {
  users,
  loading,
  loadError,
  selectedUser,
  detailOpen,
  pendingStatus,
  updatingStatus,
  loadUsers,
  openDetails,
  toggleStatus,
  cancelStatus,
  confirmStatus,
} = useUserManagementPage()

const columns: AppTableColumn<UserRow>[] = [
  { key: 'user', title: '用户' },
  { key: 'role', title: '平台角色' },
  { key: 'spaces', title: '空间数', field: 'space_count' },
  { key: 'status', title: '状态' },
  { key: 'lastLogin', title: '最近登录' },
  { key: 'actions', title: '操作' },
]

/** 用户管理需显示医院选择项；空间清单失败时仍能使用列表的其他操作。 */
async function loadTenants(): Promise<void> {
  try {
    tenants.value = (await fetchTenants()).items
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '医院列表加载失败')
  }
}

/** 新建成功后由子视图发出事件，页面重新读取权威用户列表。 */
function handleCreated(): void {
  void loadUsers()
}

onMounted(() => {
  // 用户列表与医院选项相互独立并行加载，避免任一请求失败阻断另一项内容。
  void loadUsers()
  void loadTenants()
})
</script>

<template>
  <section class="page-section">
    <div class="page-intro">
      <div>
        <p class="eyebrow">系统管理</p>
        <h1>用户管理</h1>
        <p class="page-description">创建、停用和管理平台登录账号。</p>
      </div>
      <button class="primary-button" type="button" @click="showCreateDialog = true">
        <Plus :size="16" />新建用户
      </button>
    </div>

    <div
      v-if="loadError"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px]"
      role="alert"
    >
      <strong class="text-sm text-destructive">用户数据加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ loadError }}</p>
      <button class="secondary-button" type="button" @click="loadUsers">重新加载</button>
    </div>
    <div v-else class="content-card table-card">
      <AppTable :rows="users" :columns="columns" :loading="loading" row-key="id">
        <template #cell-user="{ row }">
          <strong>{{ row.display_name }}</strong>
          <small>{{ row.login }}</small>
        </template>
        <template #cell-role="{ row }">{{ row.platform_role || '空间成员' }}</template>
        <template #cell-status="{ row }">
          <button
            class="status-pill cursor-pointer border-0"
            :class="row.status === 'active' ? 'published' : 'disabled'"
            type="button"
            :aria-label="row.status === 'active' ? `停用${row.display_name}` : `启用${row.display_name}`"
            @click="toggleStatus(row)"
          >
            {{ row.status === 'active' ? '正常' : '停用' }}
          </button>
        </template>
        <template #cell-lastLogin="{ row }">
          {{ row.last_login_at ? new Date(row.last_login_at).toLocaleString('zh-CN') : '尚未登录' }}
        </template>
        <template #cell-actions="{ row }">
          <div class="user-row-actions">
            <button class="table-action" type="button" @click="openDetails(row)">详情</button>
            <button class="table-action" type="button" @click="(editingUser = row, editDialogOpen = true)">编辑</button>
          </div>
        </template>
      </AppTable>
    </div>
  </section>

  <CreateUserDialog v-model:open="showCreateDialog" :tenants="tenants" @created="handleCreated" />
  <EditUserDialog v-model:open="editDialogOpen" :user="editingUser" :tenants="tenants" @saved="loadUsers" />
  <UserDetailDialog :open="detailOpen" :user="selectedUser" @close="detailOpen = false" />
  <AppConfirmDialog
    :open="Boolean(pendingStatus)"
    :title="pendingStatus ? `确认停用“${pendingStatus.display_name}”？` : '确认停用用户'"
    description="停用后该用户将无法登录平台，已有的空间和知识库授权不会被删除。"
    confirm-label="确认停用"
    :busy="updatingStatus"
    @update:open="(open) => !open && cancelStatus()"
    @confirm="confirmStatus"
  />
</template>

<style scoped lang="scss" src="./index.scss"></style>
