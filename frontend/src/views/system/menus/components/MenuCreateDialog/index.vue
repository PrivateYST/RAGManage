<!-- 菜单创建弹窗：维护目录、页面或按钮节点的表单输入。 -->
<script setup lang="ts">
import type { MenuCreateDialogEmits, MenuCreateDialogProps } from './type'
import { watch } from 'vue'
import { AppDialog } from '@/components'
import { useMenuCreateDialog } from './index'

const props = defineProps<MenuCreateDialogProps>()
const emit = defineEmits<MenuCreateDialogEmits>()
const { form, reset } = useMenuCreateDialog()

/** 复制表单快照给父级，弹窗不直接依赖 API 层。 */
function submit(): void {
  emit('submit', { ...form.value })
}

watch(
  () => props.open,
  (open) => open && reset(),
)
</script>

<template>
  <AppDialog
    :open="open"
    title="新增菜单"
    content-class="w-[min(520px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <form class="dialog-card" @submit.prevent="submit">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">系统管理</p>
          <h2>新增菜单</h2>
        </div>
        <button type="button" class="dialog-close" @click="emit('close')">关闭</button>
      </div>
      <div class="grid gap-[12px] sm:grid-cols-2">
        <label>编码<input v-model.trim="form.code" required pattern="[a-z0-9][a-z0-9_-]+" /></label>
        <label>名称<input v-model.trim="form.name" required maxlength="80" /></label>
        <label
          >类型<select v-model="form.kind">
            <option value="directory">目录</option>
            <option value="menu">页面</option>
            <option value="button">按钮</option>
          </select></label
        >
        <label
          >父级菜单<select v-model="form.parent_id">
            <option value="">顶级菜单</option>
            <option v-for="menu in menus" :key="menu.id" :value="menu.id">{{ menu.name }}</option>
          </select></label
        >
        <label>路由<input v-model.trim="form.route" placeholder="/system/example" /></label>
        <label>图标<input v-model.trim="form.icon" placeholder="Activity" /></label>
        <label
          >权限标识<input v-model.trim="form.permission_code" required placeholder="example:view"
        /></label>
        <label
          >排序<input v-model.number="form.sort_order" type="number" min="0" max="9999" required
        /></label>
      </div>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="emit('close')">取消</button
        ><button class="primary-button" :disabled="submitting">
          {{ submitting ? '创建中…' : '创建菜单' }}
        </button>
      </div>
    </form>
  </AppDialog>
</template>
