<!-- 角色管理页面：展示平台角色与权限范围，并保护系统内置角色。 -->
<script setup lang="ts">
import type { RoleRow } from './type'
import type { AppTableColumn } from '@/components'
import { onMounted } from 'vue'
import { AppTable } from '@/components'
import { useRolesPage } from './index'

const { roles, loading, loadError, syncingRoleId, loadRoles, syncRoleMenus } = useRolesPage()
const columns: AppTableColumn<RoleRow>[] = [
  { key: 'name', title: '角色' },
  { key: 'scope', title: '作用域', field: 'scope' },
  { key: 'permissions', title: '权限数' },
  { key: 'actions', title: '操作' },
]

onMounted(() => void loadRoles())
</script>

<template>
  <section class="page-section">
    <div class="page-intro">
      <div>
        <p class="eyebrow">系统管理</p>
        <h1>角色管理</h1>
        <p class="page-description">配置平台、空间和知识库角色的操作范围。</p>
      </div>
    </div>
    <div v-if="loading" class="content-card module-placeholder" role="status">
      <span class="loading-spinner" />
      <p>正在加载角色…</p>
    </div>
    <div
      v-else-if="loadError"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px]"
      role="alert"
    >
      <strong class="text-sm text-destructive">角色列表加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ loadError }}</p>
      <button class="secondary-button" type="button" @click="loadRoles">重新加载</button>
    </div>
    <div v-else class="content-card table-card">
      <AppTable :rows="roles" :columns="columns" :loading="loading" row-key="id">
        <template #cell-name="{ row }"
          ><strong>{{ row.name }}</strong
          ><small>{{ row.code }}</small></template
        >
        <template #cell-permissions="{ row }">{{ row.menu_ids.length }} 项</template>
        <template #cell-actions="{ row }">
          <button
            class="table-action"
            type="button"
            :disabled="row.is_system || syncingRoleId === row.id"
            @click="syncRoleMenus(row)"
          >
            {{
              row.is_system ? '系统角色' : syncingRoleId === row.id ? '同步中…' : '同步当前菜单权限'
            }}
          </button>
        </template>
      </AppTable>
    </div>
  </section>
</template>

<style scoped lang="scss" src="./index.scss"></style>
