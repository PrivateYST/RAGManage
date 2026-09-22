<script setup lang="ts">
import { computed, nextTick, useTemplateRef, watch } from 'vue'
import { Bot, Database, Plus } from '@/components'
import ChatComposer from './components/ChatComposer.vue'
import ChatMessage from './components/ChatMessage.vue'
import CitationPanel from './components/CitationPanel.vue'
import ConversationList from './components/ConversationList.vue'
import { useChatRun } from './index'
import './index.scss'

const {
  knowledgeBases,
  knowledgeBaseId,
  selectedKnowledgeBase,
  conversations,
  conversationId,
  selectedConversation,
  messages,
  question,
  loading,
  sending,
  deletingConversationId,
  canSend,
  citationPanelOpen,
  selectedCitations,
  selectConversation,
  newConversation,
  removeConversation,
  sendQuestion,
  stopGeneration,
  retry,
  resume,
  showCitations,
  closeCitations,
  feedback,
} = useChatRun()

const messageViewport = useTemplateRef<HTMLElement>('messageViewport')
const disabledReason = computed(() => (!knowledgeBaseId.value ? '当前空间暂无可访问知识库' : ''))
const latestMessageContent = computed(() => messages.value.at(-1)?.content ?? '')
let shouldFollowStream = true

function onMessageScroll(): void {
  const viewport = messageViewport.value
  if (!viewport) return
  shouldFollowStream = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= 56
}

watch([() => messages.value.length, latestMessageContent], async () => {
  if (!shouldFollowStream) return
  await nextTick()
  if (messageViewport.value) messageViewport.value.scrollTop = messageViewport.value.scrollHeight
})
</script>

<template>
  <section class="flex h-full min-h-0 w-full flex-col overflow-hidden">
    <div
      class="mb-[10px] flex min-h-[66px] shrink-0 items-start justify-between gap-[20px] max-sm:flex-col"
    >
      <div>
        <p class="eyebrow">引用问答</p>
        <h1 class="mb-[4px] mt-[2px] text-[22px] font-semibold leading-tight">知识问答</h1>
        <p class="mb-0 text-[11px] text-muted-foreground">
          回答固定使用当前 Release，并为每个来源提供可验证的原文定位。
        </p>
      </div>
      <label
        class="mt-[4px] flex h-[36px] items-center gap-[6px] rounded-md border border-border bg-card px-[10px] text-[10px] text-muted-foreground max-sm:mt-0 max-sm:w-full"
      >
        <Database :size="13" aria-hidden="true" />
        <span>知识库</span>
        <select
          v-model="knowledgeBaseId"
          class="h-[28px] min-w-[210px] border-0 bg-transparent text-[11px] text-foreground outline-none max-sm:min-w-0 max-sm:flex-1"
          :disabled="sending"
        >
          <option v-if="!knowledgeBases.length" value="">暂无知识库</option>
          <option
            v-for="knowledgeBase in knowledgeBases"
            :key="knowledgeBase.id"
            :value="knowledgeBase.id"
          >
            {{ knowledgeBase.name
            }}{{
              knowledgeBase.active_release_id
                ? ` · Release #${knowledgeBase.active_release_id}`
                : ' · 未发布'
            }}
          </option>
        </select>
      </label>
    </div>

    <div
      class="relative grid min-h-0 flex-1 overflow-hidden rounded-lg border border-border bg-card"
      :class="
        citationPanelOpen
          ? 'grid-cols-[220px_minmax(0,1fr)_320px] max-[1050px]:grid-cols-[190px_minmax(0,1fr)_280px] max-[780px]:grid-cols-1'
          : 'grid-cols-[220px_minmax(0,1fr)] max-[1050px]:grid-cols-[190px_minmax(0,1fr)] max-[780px]:grid-cols-1'
      "
    >
      <ConversationList
        :conversations="conversations"
        :active-id="conversationId"
        :disabled="sending || Boolean(deletingConversationId)"
        @select="selectConversation"
        @create="newConversation"
        @delete="removeConversation"
      />

      <main class="chat-main-panel">
        <header>
          <div>
            <strong>{{ selectedConversation?.title || '新会话' }}</strong>
            <span>{{ selectedKnowledgeBase?.name || '未选择知识库' }}</span>
          </div>
          <span v-if="selectedKnowledgeBase?.active_release_id" class="status-pill ready">
            Release #{{ selectedKnowledgeBase.active_release_id }}
          </span>
          <span v-else class="status-pill draft">索引未发布</span>
        </header>

        <div ref="messageViewport" class="chat-message-viewport" @scroll="onMessageScroll">
          <div v-if="loading" class="chat-empty-state">
            <span class="loading-spinner" /><strong>正在加载会话…</strong>
          </div>
          <div v-else-if="!messages.length" class="chat-empty-state">
            <div><Bot :size="22" aria-hidden="true" /></div>
            <strong>开始一次有依据的问答</strong>
            <span>系统会先检索当前发布版本，再生成带引用的回答。</span>
            <button type="button" :disabled="!knowledgeBaseId" @click="newConversation">
              <Plus :size="13" aria-hidden="true" />新建会话
            </button>
          </div>
          <div v-else class="chat-message-list">
            <ChatMessage
              v-for="message in messages"
              :key="message.id"
              :message="message"
              :busy="sending"
              @citations="showCitations(message.citations)"
              @retry="retry"
              @resume="resume"
              @feedback="feedback"
            />
          </div>
        </div>

        <ChatComposer
          v-model="question"
          :sending="sending"
          :can-send="canSend"
          :disabled-reason="disabledReason"
          @send="sendQuestion"
          @stop="stopGeneration"
        />
      </main>

      <CitationPanel
        :open="citationPanelOpen"
        :citations="selectedCitations"
        @close="closeCitations"
      />
    </div>
  </section>
</template>
