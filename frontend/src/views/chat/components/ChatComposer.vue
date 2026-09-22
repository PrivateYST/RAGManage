<script setup lang="ts">
import { Send, Square } from '@/components'

defineProps<{ sending: boolean; canSend: boolean; disabledReason: string }>()
const emit = defineEmits<{ send: []; stop: [] }>()
const question = defineModel<string>({ required: true })
</script>

<template>
  <form
    class="chat-composer relative grid shrink-0 grid-cols-[minmax(0,1fr)_auto] gap-x-[10px] gap-y-[6px] border-t border-border bg-card px-[14px] py-[10px]"
    @submit.prevent="emit('send')"
  >
    <textarea
      v-model="question"
      class="col-span-2 row-start-1 min-h-[62px] w-full resize-none rounded-md border border-border bg-background px-[10px] py-[10px] pr-[90px] text-[11px] leading-[1.55] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
      rows="2"
      maxlength="4000"
      :disabled="sending"
      :placeholder="disabledReason || '输入问题，回答将只使用当前知识库的已发布内容…'"
      @keydown.ctrl.enter="emit('send')"
    />
    <button
      v-if="sending"
      class="col-start-2 row-start-1 mb-[8px] mr-[8px] inline-flex h-[30px] items-center gap-[4px] rounded-md border border-destructive/30 bg-destructive/10 px-[10px] text-[10px] text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      type="button"
      @click="emit('stop')"
    >
      <Square :size="13" aria-hidden="true" />停止
    </button>
    <button
      v-else
      class="primary-button col-start-2 row-start-1 mb-[8px] mr-[8px] self-end"
      type="submit"
      :disabled="!canSend"
    >
      <Send :size="14" aria-hidden="true" />发送
    </button>
    <small class="col-span-2 row-start-2 pl-[10px] text-[8px] leading-[1.5] text-muted-foreground"
      >Ctrl + Enter 发送 · 回答中的引用由服务端校验</small
    >
  </form>
</template>
