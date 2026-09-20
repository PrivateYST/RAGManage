<!-- 超级管理员发放 API Key 的标准化表单弹窗。 -->
<script setup lang="ts">
import type { ApiKeyCreateDialogProps, ApiKeyCreatePayload } from './type'
import { KeyRound, X } from '@/components'
import { useApiKeyCreateDialog } from './index'
import './index.scss'

const props = defineProps<ApiKeyCreateDialogProps>()
const emit = defineEmits<{
  close: []
  submit: [payload: ApiKeyCreatePayload]
}>()
const { form, error, submit } = useApiKeyCreateDialog(props, (event, payload) => emit(event, payload))
</script>

<template>
  <div v-if="open" class="api-key-dialog-backdrop" @click.self="emit('close')">
    <section class="api-key-dialog" role="dialog" aria-modal="true" aria-labelledby="api-key-dialog-title">
      <header class="api-key-dialog-header">
        <div class="api-key-dialog-heading">
          <KeyRound :size="17" />
          <div>
            <p class="eyebrow">
              公司凭据
            </p><h2 id="api-key-dialog-title">
              发放 API Key
            </h2>
          </div>
        </div>
        <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </header>
      <p class="api-key-dialog-description">
        Key 由公司超级管理员创建并下发，客户不能自行生成或管理。
      </p>
      <form class="api-key-form" @submit.prevent="submit">
        <label>客户空间<select v-model="form.tenantId" required><option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">{{ tenant.name }}</option></select></label>
        <label>Key 名称<input v-model="form.name" maxlength="120" placeholder="例如：客户 A 生产环境" required></label>
        <label>Token 总额度<input v-model="form.tokenLimit" type="number" min="1" max="10000000000" step="1" required><small>嵌入输入、生成输入和生成输出共用额度。</small></label>
        <label>有效期（可选）<input v-model="form.expiresAt" type="date"><small>留空表示不过期；公司可随时撤销。</small></label>
        <p v-if="error" class="api-key-field-error" role="alert">
          {{ error }}
        </p>
        <footer class="api-key-dialog-actions">
          <button type="button" class="secondary-button" @click="emit('close')">
            取消
          </button><button type="submit" class="primary-button" :disabled="submitting">
            {{ submitting ? '创建中…' : '创建并显示 Key' }}
          </button>
        </footer>
      </form>
    </section>
  </div>
</template>
