<script setup lang="ts">
import { Send, Square } from '@/components'

defineProps<{ sending: boolean, canSend: boolean, disabledReason: string }>()
const emit = defineEmits<{ send: [], stop: [] }>()
const question = defineModel<string>({ required: true })
</script>

<template>
  <form class="chat-composer" @submit.prevent="emit('send')">
    <textarea
      v-model="question"
      rows="2"
      maxlength="4000"
      :disabled="sending"
      :placeholder="disabledReason || '输入问题，回答将只使用当前知识库的已发布内容…'"
      @keydown.ctrl.enter="emit('send')"
    />
    <button v-if="sending" class="chat-stop-button" type="button" @click="emit('stop')">
      <Square :size="13" aria-hidden="true" />停止
    </button>
    <button v-else class="primary-button" type="submit" :disabled="!canSend">
      <Send :size="14" aria-hidden="true" />发送
    </button>
    <small>Ctrl + Enter 发送 · 回答中的引用由服务端校验</small>
  </form>
</template>
