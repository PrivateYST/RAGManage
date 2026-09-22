<!-- 超级管理员发放 API Key 的标准化表单弹窗。 -->
<script setup lang="ts">
import type { ApiKeyCreateDialogProps, ApiKeyCreatePayload } from './type'
import { AppDialog, KeyRound, X } from '@/components'
import { useApiKeyCreateDialog } from './index'
import './index.scss'

const props = defineProps<ApiKeyCreateDialogProps>()
const emit = defineEmits<{
  close: []
  submit: [payload: ApiKeyCreatePayload]
}>()
const { form, error, submit } = useApiKeyCreateDialog(props, (event, payload) =>
  emit(event, payload),
)
</script>

<template>
  <AppDialog
    :open="open"
    title="生成医院网关 Key"
    content-class="w-[min(480px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <section class="api-key-dialog">
      <header class="api-key-dialog-header">
        <div class="api-key-dialog-heading">
          <KeyRound :size="17" />
          <div>
            <p class="eyebrow">公司凭据</p>
            <h2 id="api-key-dialog-title">生成医院网关 Key</h2>
          </div>
        </div>
        <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </header>
      <p class="api-key-dialog-description">
        系统会为医院创建一个隐藏的 Open WebUI 服务账号，并生成一把原生 API
        Key；医院员工无需逐个注册。
      </p>
      <form class="api-key-form" @submit.prevent="submit">
        <label
          >客户空间<select v-model="form.tenantId" required>
            <option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">
              {{ tenant.name }}
            </option>
          </select></label
        >
        <label
          >Key 名称<input
            v-model="form.name"
            maxlength="120"
            placeholder="例如：客户 A 生产环境"
            required
        /></label>
        <label
          >Token 总额度<input
            v-model="form.tokenLimit"
            type="number"
            min="1"
            max="10000000000"
            step="1"
            required
          /><small>嵌入输入、生成输入和生成输出共用额度。</small></label
        >
        <label
          >有效期（可选）<input v-model="form.expiresAt" type="date" /><small
            >留空表示不过期；公司可随时停用或删除。</small
          ></label
        >
        <p v-if="error" class="api-key-field-error" role="alert">
          {{ error }}
        </p>
        <footer class="api-key-dialog-actions">
          <button type="button" class="secondary-button" @click="emit('close')">取消</button
          ><button type="submit" class="primary-button" :disabled="submitting">
            {{ submitting ? '生成中…' : '生成并显示 Key' }}
          </button>
        </footer>
      </form>
    </section>
  </AppDialog>
</template>
