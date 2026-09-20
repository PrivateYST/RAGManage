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
  canSend,
  error,
  citationPanelOpen,
  selectedCitations,
  selectConversation,
  newConversation,
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

watch([() => messages.value.length, latestMessageContent], async () => {
  await nextTick()
  if (messageViewport.value)
    messageViewport.value.scrollTop = messageViewport.value.scrollHeight
})
</script>

<template>
  <section class="page-section chat-page">
    <div class="chat-page-header">
      <div>
        <p class="eyebrow">
          引用问答
        </p>
        <h1>知识问答</h1>
        <p>回答固定使用当前 Release，并为每个来源提供可验证的原文定位。</p>
      </div>
      <label>
        <Database :size="13" aria-hidden="true" />
        <span>知识库</span>
        <select v-model="knowledgeBaseId" :disabled="sending">
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

    <div v-if="error" class="error-banner chat-error" role="alert">
      {{ error }}
    </div>

    <div class="chat-workspace" :class="{ 'with-citations': citationPanelOpen }">
      <ConversationList
        :conversations="conversations"
        :active-id="conversationId"
        :disabled="sending"
        @select="selectConversation"
        @create="newConversation"
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

        <div ref="messageViewport" class="chat-message-viewport">
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
