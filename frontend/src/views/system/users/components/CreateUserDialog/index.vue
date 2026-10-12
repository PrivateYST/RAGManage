<!-- 新建用户弹窗：只管理账号表单和平台/医院角色映射，不承载用户列表逻辑。 -->
<script setup lang="ts">
import type { CreateUserDialogEmits, CreateUserDialogProps } from './type'
import { watch } from 'vue'
import { AppDialog } from '@/components'
import { useCreateUserDialog } from './index'

const props = defineProps<CreateUserDialogProps>()
const emit = defineEmits<CreateUserDialogEmits>()
const { form, saving, resetForm, submit } = useCreateUserDialog()

/** 创建成功后关闭弹窗并通知列表页刷新。 */
async function submitUser(): Promise<void> {
  if (await submit()) {
    emit('created')
    emit('close')
  }
}

watch(
  () => props.open,
  (open) => open && resetForm(),
)
</script>

<template>
  <AppDialog
    :open="open"
    title="新建用户"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <form class="dialog-card" @submit.prevent="submitUser">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">系统管理</p>
          <h2>新建用户</h2>
        </div>
        <button type="button" class="dialog-close" @click="emit('close')">关闭</button>
      </div>
      <label
        >登录名<input v-model.trim="form.login" required minlength="3" maxlength="120"
      /></label>
      <label>显示名称<input v-model.trim="form.display_name" required maxlength="100" /></label>
      <label
        >初始密码<input v-model="form.password" required minlength="8" type="password"
      /></label>
      <label
        >平台角色<select v-model="form.role_level">
          <option value="company_admin">系统管理员</option>
          <option value="hospital_admin">管理员</option>
          <option value="ordinary">普通用户</option>
        </select></label
      >
      <label v-if="form.role_level !== 'company_admin'"
        >所属医院<select v-model="form.tenant_id" :required="form.role_level === 'hospital_admin'">
          <option value="">暂不分配</option>
          <option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">
            {{ tenant.name }}
          </option>
        </select></label
      >
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="emit('close')">取消</button>
        <button class="primary-button" :disabled="saving">
          {{ saving ? '保存中…' : '创建用户' }}
        </button>
      </div>
    </form>
  </AppDialog>
</template>
