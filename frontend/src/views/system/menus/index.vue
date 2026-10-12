<!-- 菜单管理页面：呈现动态菜单数据并编排创建与编辑子视图。 -->
<script setup lang="ts">
import type { CreateMenuForm, MenuForm } from './type'
import type { MenuRow } from '@/api/admin'
import type { AppTableColumn } from '@/components'
import { onMounted } from 'vue'
import { AppTable } from '@/components'
import MenuCreateDialog from './components/MenuCreateDialog/index.vue'
import MenuEditDialog from './components/MenuEditDialog/index.vue'
import { useMenusPage } from './index'

const {
  menus,
  loading,
  loadError,
  editingMenu,
  creatingMenu,
  submitting,
  loadMenus,
  openEditor,
  openCreator,
  submitCreate,
  submitEdit,
  toggleVisibility,
} = useMenusPage()
const columns: AppTableColumn<MenuRow>[] = [
  { key: 'name', title: '菜单名称' },
  { key: 'kind', title: '类型' },
  { key: 'permission', title: '权限标识' },
  { key: 'route', title: '路由', field: 'route' },
  { key: 'visible', title: '显示' },
  { key: 'actions', title: '操作' },
]

/** 子弹窗只发出表单快照，页面协调提交结果与弹窗关闭时机。 */
async function handleCreate(form: CreateMenuForm): Promise<void> {
  if (await submitCreate(form)) creatingMenu.value = false
}

/** 编辑请求失败时保留目标菜单，用户可修正后重试。 */
async function handleEdit(form: MenuForm): Promise<void> {
  await submitEdit(form)
}

onMounted(() => void loadMenus())
</script>

<template>
  <section class="page-section">
    <div class="page-intro">
      <div>
        <p class="eyebrow">系统管理</p>
        <h1>菜单管理</h1>
        <p class="page-description">维护目录、页面和按钮权限标识。</p>
      </div>
      <button class="primary-button" type="button" @click="openCreator">新增菜单</button>
    </div>
    <div v-if="loading" class="content-card module-placeholder" role="status">
      <span class="loading-spinner" />
      <p>正在加载菜单…</p>
    </div>
    <div
      v-else-if="loadError"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px]"
      role="alert"
    >
      <strong class="text-sm text-destructive">菜单列表加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ loadError }}</p>
      <button class="secondary-button" type="button" @click="loadMenus">重新加载</button>
    </div>
    <div v-else class="content-card table-card">
      <AppTable :rows="menus" :columns="columns" :loading="loading" row-key="id">
        <template #cell-name="{ row }"
          ><strong>{{ row.name }}</strong
          ><small>{{ row.code }}</small></template
        >
        <template #cell-kind="{ row }">{{
          row.kind === 'directory' ? '目录' : row.kind === 'menu' ? '页面' : '按钮'
        }}</template>
        <template #cell-permission="{ row }"
          ><code>{{ row.permission_code }}</code></template
        >
        <template #cell-visible="{ row }"
          ><span class="status-pill" :class="row.visible ? 'published' : 'disabled'">{{
            row.visible ? '显示' : '隐藏'
          }}</span></template
        >
        <template #cell-actions="{ row }">
          <button class="table-action" type="button" @click="openEditor(row)">编辑</button>
          <button class="table-action" type="button" @click="toggleVisibility(row)">
            {{ row.visible ? '隐藏' : '显示' }}
          </button>
        </template>
      </AppTable>
    </div>
  </section>
  <MenuEditDialog
    :menu="editingMenu"
    :menus="menus"
    :submitting="submitting"
    @close="editingMenu = null"
    @submit="handleEdit"
  />
  <MenuCreateDialog
    :open="creatingMenu"
    :menus="menus"
    :submitting="submitting"
    @close="creatingMenu = false"
    @submit="handleCreate"
  />
</template>

<style scoped lang="scss" src="./index.scss"></style>
