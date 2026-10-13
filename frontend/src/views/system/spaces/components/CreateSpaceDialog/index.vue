<!-- 新建客户空间表单：仅负责空间编码和名称录入。 -->
<script setup lang="ts">
import type { CreateSpaceDialogProps } from './type'
import { watch } from 'vue'
import { AppDialog } from '@/components'
import { useCreateSpaceDialog } from './index'

const props = defineProps<CreateSpaceDialogProps>()
const emit = defineEmits<{
  close: []
  submit: [form: { code: string; name: string }]
}>()
const { form, reset, handleCodeInput } = useCreateSpaceDialog()

/** 创建成功后的关闭由父级控制，失败时表单保留以便修正重试。 */
function submitForm(): void {
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
    title="新建客户空间"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <form class="dialog-card" @submit.prevent="submitForm">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">平台管理</p>
          <h2>新建客户空间</h2>
        </div>
        <button type="button" class="dialog-close" @click="emit('close')">关闭</button>
      </div>
      <label
        >空间名称<input v-model.trim="form.name" required minlength="2" maxlength="120"
      /></label>
      <label
        >空间编码<input
          v-model.trim="form.code"
          required
          minlength="2"
          maxlength="64"
          pattern="[a-zA-Z0-9][a-zA-Z0-9_-]+"
          placeholder="例如 customer-a"
          @input="handleCodeInput"
      /></label>
      <small class="text-[11px] text-muted-foreground">
        编码仅支持字母、数字、短横线和下划线；大写字母会自动转为小写。
      </small>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="emit('close')">取消</button>
        <button class="primary-button" :disabled="saving">
          {{ saving ? '保存中…' : '创建空间' }}
        </button>
      </div>
    </form>
  </AppDialog>
</template>
