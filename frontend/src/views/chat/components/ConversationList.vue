<script setup lang="ts">
import type { ConversationRow } from '@/api/chat'
import { MessageSquare, Plus } from '@/components'

defineProps<{
  conversations: ConversationRow[]
  activeId: string
  disabled: boolean
}>()

const emit = defineEmits<{
  select: [conversationId: string]
  create: []
}>()

function formatDate(value: string): string {
  const date = new Date(value)
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}
</script>

<template>
  <aside class="chat-conversation-panel">
    <header>
      <div><MessageSquare :size="14" aria-hidden="true" /><strong>会话记录</strong></div>
      <button type="button" :disabled="disabled" aria-label="新建会话" @click="emit('create')">
        <Plus :size="14" aria-hidden="true" />
      </button>
    </header>
    <div v-if="conversations.length" class="chat-conversation-list">
      <button
        v-for="conversation in conversations"
        :key="conversation.id"
        type="button"
        :class="{ active: conversation.id === activeId }"
        :disabled="disabled"
        @click="emit('select', conversation.id)"
      >
        <strong>{{ conversation.title }}</strong>
        <span
          >{{ conversation.message_count }} 条消息 · {{ formatDate(conversation.updated_at) }}</span
        >
      </button>
    </div>
    <div v-else class="chat-conversation-empty">
      <span>还没有会话</span>
      <small>发送第一个问题后会自动创建。</small>
    </div>
  </aside>
</template>
