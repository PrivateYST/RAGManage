<!--
  问答会话列表：负责会话选择、新建入口和删除确认 UI；数据读写通过 props 与 emits 交给页面逻辑。
  列表区域使用独立滚动容器，避免会话较多时挤压主问答面板。
-->
<script setup lang="ts">
import type { ConversationListEmits, ConversationListProps } from './type'
import { AppConfirmDialog, MessageSquare, Plus, Trash2 } from '@/components'
import { useConversationList } from './index'

const props = defineProps<ConversationListProps>()

const emit = defineEmits<ConversationListEmits>()

const {
  pendingDelete,
  hoveredConversationId,
  deleteDialogOpen,
  formatDate,
  requestDelete,
  confirmDelete,
  handleConversationEnter,
  handleConversationLeave,
} = useConversationList(props, emit)
</script>

<template>
  <aside class="flex min-w-0 flex-col border-r border-border bg-secondary max-[780px]:hidden">
    <header
      class="flex min-h-[48px] shrink-0 items-center justify-between border-b border-border px-[14px]"
    >
      <div class="flex items-center gap-[6px] text-muted-foreground">
        <MessageSquare :size="14" aria-hidden="true" /><strong class="text-[11px]">会话记录</strong>
      </div>
      <button
        class="grid size-[28px] place-items-center rounded-md border-0 bg-primary/10 text-primary transition-colors hover:bg-primary/20 disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        type="button"
        :disabled="disabled"
        aria-label="新建会话"
        @click="emit('create')"
      >
        <Plus :size="14" aria-hidden="true" />
      </button>
    </header>
    <div
      v-if="conversations.length"
      class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-[6px] [scrollbar-gutter:stable]"
    >
      <div
        v-for="conversation in conversations"
        :key="conversation.id"
        class="group flex min-h-[58px] w-full items-center gap-[4px] rounded-md px-[6px] py-[4px] transition-colors hover:bg-background"
        :class="conversation.id === activeId ? 'bg-primary/10' : ''"
        @mouseenter="handleConversationEnter(conversation.id)"
        @mouseleave="handleConversationLeave(conversation.id)"
      >
        <button
          type="button"
          class="flex min-w-0 flex-1 flex-col justify-center gap-[4px] rounded-md border-0 bg-transparent px-[8px] py-[6px] text-left text-muted-foreground transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          :disabled="disabled"
          @click="emit('select', conversation.id)"
        >
          <strong
            class="w-full truncate text-[12px] font-medium text-foreground"
            :class="conversation.id === activeId ? 'text-primary' : ''"
            >{{ conversation.title }}</strong
          >
          <span class="text-[10px]"
            >{{ conversation.message_count }} 条消息 ·
            {{ formatDate(conversation.updated_at) }}</span
          >
        </button>
        <button
          type="button"
          class="grid size-[28px] shrink-0 place-items-center rounded-md border-0 text-muted-foreground transition-opacity hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 focus-visible:pointer-events-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50"
          :class="
            hoveredConversationId === conversation.id
              ? 'pointer-events-auto opacity-100'
              : 'pointer-events-none opacity-0'
          "
          :disabled="disabled"
          :aria-label="`删除会话：${conversation.title}`"
          @click="requestDelete(conversation)"
        >
          <Trash2 :size="14" aria-hidden="true" />
        </button>
      </div>
    </div>
    <div
      v-else
      class="flex flex-1 flex-col items-center justify-center text-center text-[10px] text-muted-foreground"
    >
      <span>还没有会话</span>
      <small class="mt-[4px] text-[9px]">发送第一个问题后会自动创建。</small>
    </div>
    <AppConfirmDialog
      v-model:open="deleteDialogOpen"
      title="删除这条会话？"
      :description="`删除后会话将从列表中移除，但历史记录会保留在系统审计中。${pendingDelete ? `当前会话：${pendingDelete.title}` : ''}`"
      confirm-label="删除会话"
      @confirm="confirmDelete"
    />
  </aside>
</template>
