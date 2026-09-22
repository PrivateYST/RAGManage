<!-- 创建成功后的明文 Key 通过受保护接口展示，关闭后列表仍可由管理员复制。 -->
<script setup lang="ts">
import type { ApiKeyRevealDialogProps } from './type'
import { AppDialog, Copy, KeyRound, X } from '@/components'
import { useApiKeyRevealDialog } from './index'
import './index.scss'

const props = defineProps<ApiKeyRevealDialogProps>()
const emit = defineEmits<{ close: []; copied: [] }>()
const { copying, copy } = useApiKeyRevealDialog(props, (event) => emit(event))
</script>

<template>
  <AppDialog
    :open="Boolean(apiKey)"
    title="API Key 已创建"
    content-class="w-[min(560px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <section v-if="apiKey" class="api-key-reveal-card">
      <header>
        <div class="api-key-reveal-heading">
          <KeyRound :size="17" />
          <div>
            <p class="eyebrow">仅显示一次 / 安全复制</p>
            <h2 id="api-key-reveal-title">API Key 已创建</h2>
          </div>
        </div>
        <button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </header>
      <p>请复制后通过公司安全渠道下发给客户。列表中的“复制完整 Key”会再次通过管理员接口查询。</p>
      <div class="api-key-raw-value">
        <code>{{ apiKey.raw_key }}</code
        ><button type="button" class="secondary-button" :disabled="copying" @click="copy">
          <Copy :size="14" />{{ copying ? '复制中' : '复制' }}
        </button>
      </div>
      <footer>
        <button type="button" class="primary-button" @click="emit('close')">我已安全保存</button>
      </footer>
    </section>
  </AppDialog>
</template>
