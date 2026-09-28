<!-- 平台管理员替换模型网关 API Key；明文仅存在于当前输入控件。 -->
<script setup lang="ts">
import type { GatewayApiKeyDialogProps } from './type'
import { AppDialog, Eye, KeyRound, X } from '@/components'
import { useGatewayApiKeyDialog } from './index'
import './index.scss'

const props = defineProps<GatewayApiKeyDialogProps>()
const emit = defineEmits<{ close: []; saved: [] }>()
const { form, status, loading, submitting, showKey, error, submit } = useGatewayApiKeyDialog(
  props,
  (event) => (event === 'close' ? emit('close') : emit('saved')),
)
</script>

<template>
  <AppDialog
    :open="open"
    title="配置全局网关 Key"
    content-class="w-[min(520px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <section class="gateway-key-dialog">
      <header class="gateway-key-dialog-header">
        <div class="gateway-key-dialog-heading">
          <KeyRound :size="17" />
          <div>
            <p class="eyebrow">模型网关</p>
            <h2 id="gateway-key-dialog-title">配置全局网关 Key</h2>
          </div>
        </div>
        <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </header>
      <p class="gateway-key-dialog-description">
        这里配置公司 Open WebUI 管理
        Key。保存后会立即替换系统全局凭据，用于模型请求和为医院创建服务账号；该 Key 不会下发给医院。
      </p>
      <div v-if="loading" class="gateway-key-status" role="status" aria-live="polite">
        正在读取当前配置…
      </div>
      <div v-else class="gateway-key-status">
        <span>当前状态</span>
        <strong>{{ status?.configured ? status.masked : '未配置' }}</strong>
        <small>{{ status?.source === 'system' ? '系统内配置' : '环境变量配置' }}</small>
      </div>
      <!--
        密钥输入是敏感配置的唯一明文边界：表单只反馈忙碌状态和通用错误，
        不把密钥值写入状态文本或异常描述，避免辅助技术和日志意外读取凭据。
      -->
      <form
        class="gateway-key-form"
        :aria-busy="submitting || loading ? 'true' : 'false'"
        @submit.prevent="submit"
      >
        <label
          >新的全局模型网关 Key
          <div class="gateway-key-input-wrap">
            <input
              v-model="form.apiKey"
              :type="showKey ? 'text' : 'password'"
              autocomplete="new-password"
              maxlength="500"
              placeholder="粘贴 Open WebUI 全局管理 Key"
              required
              :aria-invalid="error ? 'true' : 'false'"
              :aria-describedby="error ? 'gateway-key-form-error' : undefined"
            />
            <button
              type="button"
              class="gateway-key-visibility"
              :aria-label="showKey ? '隐藏 API Key' : '显示 API Key'"
              @click="showKey = !showKey"
            >
              <Eye :size="15" />
            </button>
          </div>
        </label>
        <p
          v-if="error"
          id="gateway-key-form-error"
          class="gateway-key-field-error"
          role="alert"
          aria-live="polite"
        >
          {{ error }}
        </p>
        <footer class="gateway-key-dialog-actions">
          <button type="button" class="secondary-button" @click="emit('close')">取消</button>
          <button
            type="submit"
            class="primary-button"
            :disabled="submitting || loading"
            :aria-busy="submitting ? 'true' : 'false'"
          >
            <span v-if="submitting" role="status" aria-live="polite">保存中…</span>
            <template v-else>保存并立即启用全局 Key</template>
          </button>
        </footer>
      </form>
    </section>
  </AppDialog>
</template>
