<!-- 创建成功后的明文 Key 只展示一次，关闭后无法从服务端找回。 -->
<script setup lang="ts">
import type { ApiKeyRevealDialogProps } from './type'
import { Copy, KeyRound, X } from '@/components'
import { useApiKeyRevealDialog } from './index'
import './index.scss'

const props = defineProps<ApiKeyRevealDialogProps>()
const emit = defineEmits<{ close: [], copied: [] }>()
const { copying, copyError, copy } = useApiKeyRevealDialog(props, event => emit(event))
</script>

<template>
  <div v-if="apiKey" class="api-key-reveal-backdrop">
    <section class="api-key-reveal-card" role="dialog" aria-modal="true" aria-labelledby="api-key-reveal-title">
      <header>
        <div class="api-key-reveal-heading">
          <KeyRound :size="17" /><div>
            <p class="eyebrow">
              仅显示一次
            </p><h2 id="api-key-reveal-title">
              API Key 已创建
            </h2>
          </div>
        </div><button class="icon-button" type="button" aria-label="关闭" @click="emit('close')">
          <X :size="16" />
        </button>
      </header>
      <p>请复制后通过公司安全渠道下发给客户。关闭后系统不会再次显示明文。</p>
      <div class="api-key-raw-value">
        <code>{{ apiKey.raw_key }}</code><button type="button" class="secondary-button" :disabled="copying" @click="copy">
          <Copy :size="14" />{{ copying ? '复制中' : '复制' }}
        </button>
      </div>
      <p v-if="copyError" class="api-key-copy-error" role="alert">
        {{ copyError }}
      </p>
      <footer>
        <button type="button" class="primary-button" @click="emit('close')">
          我已安全保存
        </button>
      </footer>
    </section>
  </div>
</template>
