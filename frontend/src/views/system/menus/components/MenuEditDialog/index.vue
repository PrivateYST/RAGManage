<!-- 菜单编辑弹窗：编辑安全元数据，路由与权限编码由系统白名单管理。 -->
<script setup lang="ts">
import type { MenuEditDialogEmits, MenuEditDialogProps } from './type'
import { AppDialog } from '@/components'
import { useMenuEditDialog } from './index'

const props = defineProps<MenuEditDialogProps>()
const emit = defineEmits<MenuEditDialogEmits>()
const { form } = useMenuEditDialog(props)

/** 提交当前表单快照，父级负责请求和成功后的关闭。 */
function submit(): void {
  emit('submit', { ...form.value })
}
</script>

<template>
  <AppDialog
    :open="Boolean(menu)"
    title="编辑菜单"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <form v-if="menu" class="dialog-card" @submit.prevent="submit">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">系统管理</p>
          <h2>编辑菜单</h2>
        </div>
        <button type="button" class="dialog-close" @click="emit('close')">关闭</button>
      </div>
      <label>菜单名称<input v-model.trim="form.name" required maxlength="80" /></label>
      <label
        >父级菜单<select v-model="form.parent_id">
          <option value="">顶级菜单</option>
          <option
            v-for="item in menus"
            :key="item.id"
            :value="item.id"
            :disabled="item.id === menu.id"
          >
            {{ item.name }}
          </option>
        </select></label
      >
      <label
        >排序<input v-model.number="form.sort_order" type="number" min="0" max="9999" required
      /></label>
      <label
        >状态<select v-model="form.status">
          <option value="active">启用</option>
          <option value="disabled">停用</option>
        </select></label
      >
      <p class="text-xs text-muted-foreground">
        路由和权限标识由系统维护，编辑后会立即影响菜单展示。
      </p>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="emit('close')">取消</button
        ><button class="primary-button" :disabled="submitting">
          {{ submitting ? '保存中…' : '保存菜单' }}
        </button>
      </div>
    </form>
  </AppDialog>
</template>
