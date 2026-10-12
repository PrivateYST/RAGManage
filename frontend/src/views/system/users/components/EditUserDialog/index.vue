<!-- 用户编辑弹窗：维护显示名称和可选密码，角色与登录名由既有接口保护。 -->
<script setup lang="ts">
import type { EditUserDialogEmits, EditUserDialogProps } from './type'
import { AppDialog } from '@/components'
import { useEditUserDialog } from './index'

const props = defineProps<EditUserDialogProps>()
const emit = defineEmits<EditUserDialogEmits>()
const { displayName, password, roleLevel, tenantId, detail, saving, save } = useEditUserDialog(
  () => props.user,
  props.tenants,
)

/** 保存成功后通知父页面刷新权威列表并关闭编辑器。 */
async function submit(): Promise<void> {
  if (await save()) {
    emit('saved')
    emit('update:open', false)
  }
}
</script>

<template>
  <AppDialog
    :open="open"
    title="编辑用户"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @update:open="(value) => emit('update:open', value)"
    @close="emit('update:open', false)"
  >
    <form v-if="user" class="dialog-card" @submit.prevent="submit">
      <div class="dialog-heading">
        <div><p class="eyebrow">系统管理</p><h2>编辑用户</h2></div>
        <button type="button" class="dialog-close" @click="emit('update:open', false)">关闭</button>
      </div>
      <label>登录名<input :value="user.login" disabled /></label>
      <label>显示名称<input v-model.trim="displayName" required maxlength="100" /></label>
      <label>平台角色<select v-model="roleLevel">
        <option value="company_admin">系统管理员</option>
        <option value="hospital_admin">管理员</option>
        <option value="ordinary">普通用户</option>
      </select></label>
      <label v-if="roleLevel !== 'company_admin'">所属医院<select v-model="tenantId" :required="roleLevel === 'hospital_admin'">
        <option value="">暂不分配</option>
        <option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">{{ tenant.name }}</option>
      </select></label>
      <p v-if="detail?.memberships.length" class="text-xs text-muted-foreground">
        当前有效空间：{{ detail.memberships.filter(item => item.status === 'active').map(item => item.tenant_name).join('、') || '无' }}
      </p>
      <label>重置密码（选填）<input v-model="password" minlength="8" type="password" autocomplete="new-password" /></label>
      <p class="text-xs text-muted-foreground">留空表示保持当前密码不变。</p>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" :disabled="saving" @click="emit('update:open', false)">取消</button>
        <button class="primary-button" :disabled="saving">{{ saving ? '保存中…' : '保存修改' }}</button>
      </div>
    </form>
  </AppDialog>
</template>
