<script setup lang="ts">
import type { EndpointSubmitPayload } from '@/views/models/type'
import type { EndpointFormDialogProps } from './type'
import { X } from '@/components'
import { useEndpointForm } from './index'
import './index.scss'

const props = defineProps<EndpointFormDialogProps>()
const emit = defineEmits<{ close: []; submit: [payload: EndpointSubmitPayload] }>()
const { form, error, submit } = useEndpointForm(props, (event, payload) => emit(event, payload))
</script>

<template>
  <div v-if="open" class="dialog-backdrop" @click.self="emit('close')">
    <section class="dialog-card endpoint-dialog" aria-labelledby="endpoint-dialog-title">
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">模型网关</p>
          <h2 id="endpoint-dialog-title">
            {{ endpoint ? '编辑模型端点' : '登记模型端点' }}
          </h2>
        </div>
        <button type="button" class="dialog-close" aria-label="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </header>
      <p class="dialog-description">仅保存密钥引用；API Key 继续由服务端环境变量提供。</p>
      <form @submit.prevent="submit">
        <label>端点名称<input v-model="form.name" required maxlength="120" /></label>
        <div class="endpoint-form-grid">
          <label
            >服务提供方<input v-model="form.provider" required :disabled="Boolean(endpoint)"
          /></label>
          <label
            >模型用途<select v-model="form.endpointType" :disabled="Boolean(endpoint)">
              <option value="generation">生成模型</option>
              <option value="embedding">嵌入模型</option>
              <option value="reranker">重排模型</option>
            </select></label
          >
        </div>
        <label
          >网关地址<input
            v-model="form.baseUrl"
            type="url"
            required
            placeholder="http://gateway.internal:8080"
        /></label>
        <label
          >模型白名单<textarea v-model="form.modelsText" required placeholder="每行一个模型名称" />
        </label>
        <label>密钥引用<input value="env:MODEL_GATEWAY_API_KEY" disabled /></label>
        <p v-if="error" class="field-error">
          {{ error }}
        </p>
        <footer class="dialog-actions">
          <button type="button" class="secondary-button" @click="emit('close')">取消</button
          ><button type="submit" class="primary-button">保存端点</button>
        </footer>
      </form>
    </section>
  </div>
</template>
