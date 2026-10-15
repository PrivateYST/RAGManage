<!-- 单条问答消息：呈现内容、状态和回答动作，通过事件交由工作区执行。 -->
<script setup lang="ts">
import type { ChatMessageEmits, ChatMessageProps } from './type'
import { defineAsyncComponent } from 'vue'
import { BookOpen, RefreshCw, ThumbsDown, ThumbsUp, UserRound } from '@/components'
import { useChatMessage } from './index'

defineProps<ChatMessageProps>()
const emit = defineEmits<ChatMessageEmits>()

// Markdown 引擎体积较大，仅在出现助手正文时加载，聊天页空会话不承担渲染器下载成本。
const MarkdownContent = defineAsyncComponent(() => import('../MarkdownContent/index.vue'))

const { stateLabel, outcomeLabel } = useChatMessage()
</script>

<template>
  <article class="chat-message" :class="message.role">
    <div class="chat-message-avatar">
      <UserRound v-if="message.role === 'user'" :size="15" aria-hidden="true" />
      <span v-else>R</span>
    </div>
    <div class="chat-message-content">
      <header>
        <strong>{{ message.role === 'user' ? '你' : '知识库助手' }}</strong>
        <span v-if="message.release_id">Release #{{ message.release_id }}</span>
        <span
          v-if="message.role === 'assistant' && outcomeLabel(message)"
          class="chat-outcome"
          :class="message.outcome ?? ''"
          >{{ outcomeLabel(message) }}</span
        >
      </header>
      <MarkdownContent
        v-if="message.role === 'assistant' && message.content"
        :content="message.content"
        :final="!['pending', 'generating'].includes(message.state)"
      />
      <p v-else-if="message.content" class="chat-message-text">
        {{ message.content }}
      </p>
      <p v-else-if="stateLabel(message)" class="chat-message-state" :class="message.state">
        <span
          v-if="message.state === 'generating' || message.state === 'pending'"
          class="loading-spinner"
        />
        {{ stateLabel(message) }}
      </p>
      <footer v-if="message.role === 'assistant'">
        <button v-if="message.citations.length" type="button" @click="emit('citations', message)">
          <BookOpen :size="12" aria-hidden="true" />{{ message.citations.length }} 条引用
        </button>
        <button
          v-if="message.run_id && ['pending', 'generating'].includes(message.state)"
          type="button"
          :disabled="busy"
          @click="emit('resume', message)"
        >
          <RefreshCw :size="12" aria-hidden="true" />继续接收
        </button>
        <button
          v-if="['failed', 'cancelled'].includes(message.state)"
          type="button"
          :disabled="busy"
          @click="emit('retry', message)"
        >
          <RefreshCw :size="12" aria-hidden="true" />重新生成
        </button>
        <span v-if="message.state === 'complete' && !message.hidden" class="chat-feedback-actions">
          <button
            type="button"
            aria-label="回答有帮助"
            :class="{ active: message.feedback_rating === 'helpful' }"
            @click="emit('feedback', message, 'helpful')"
          >
            <ThumbsUp :size="12" aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="回答没有帮助"
            :class="{ active: message.feedback_rating === 'not_helpful' }"
            @click="emit('feedback', message, 'not_helpful')"
          >
            <ThumbsDown :size="12" aria-hidden="true" />
          </button>
        </span>
      </footer>
    </div>
  </article>
</template>

<style scoped lang="scss" src="./index.scss"></style>
