import type { KnowledgeBaseRow } from '../../api/admin'
import type { ChatMessageRow, Citation, ConversationRow, GenerationRun, SseMessage } from '../../api/chat'
import { computed, onUnmounted, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '../../api/admin'
import {
  cancelRun,
  createConversation,
  createRun,
  fetchConversation,
  fetchConversations,
  fetchRun,
  retryRun,
  saveMessageFeedback,
  streamRun,
} from '../../api/chat'
import { useAuthStore } from '../../stores/auth'

function requestId(): string {
  return crypto.randomUUID()
}

export function useChatRun() {
  const auth = useAuthStore()
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const knowledgeBaseId = shallowRef('')
  const conversations = ref<ConversationRow[]>([])
  const conversationId = shallowRef('')
  const messages = ref<ChatMessageRow[]>([])
  const question = shallowRef('')
  const currentRun = shallowRef<GenerationRun | null>(null)
  const loading = shallowRef(true)
  const sending = shallowRef(false)
  const error = shallowRef('')
  const citationPanelOpen = shallowRef(false)
  const selectedCitations = ref<Citation[]>([])
  let streamController: AbortController | null = null

  const selectedKnowledgeBase = computed(() =>
    knowledgeBases.value.find(item => item.id === knowledgeBaseId.value) ?? null,
  )
  const selectedConversation = computed(() =>
    conversations.value.find(item => item.id === conversationId.value) ?? null,
  )
  const canSend = computed(() =>
    Boolean(knowledgeBaseId.value && question.value.trim()) && !sending.value,
  )

  async function loadKnowledgeBases(): Promise<void> {
    error.value = ''
    if (!auth.activeSpaceId) {
      knowledgeBases.value = []
      knowledgeBaseId.value = ''
      return
    }
    try {
      knowledgeBases.value = (await fetchKnowledgeBases(auth.activeSpaceId)).items
      if (!knowledgeBases.value.some(item => item.id === knowledgeBaseId.value)) {
        knowledgeBaseId.value = knowledgeBases.value.find(item => item.active_release_id)?.id
          ?? knowledgeBases.value[0]?.id
          ?? ''
      }
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '知识库加载失败'
    }
  }

  async function loadConversations(): Promise<void> {
    messages.value = []
    currentRun.value = null
    if (!knowledgeBaseId.value) {
      conversations.value = []
      conversationId.value = ''
      loading.value = false
      return
    }
    loading.value = true
    error.value = ''
    try {
      conversations.value = (await fetchConversations(knowledgeBaseId.value)).items
      if (!conversations.value.some(item => item.id === conversationId.value))
        conversationId.value = conversations.value[0]?.id ?? ''
      if (conversationId.value)
        await loadConversation(conversationId.value)
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '会话加载失败'
    }
    finally {
      loading.value = false
    }
  }

  async function loadConversation(targetId = conversationId.value): Promise<void> {
    if (!targetId) {
      messages.value = []
      return
    }
    const detail = await fetchConversation(targetId)
    messages.value = detail.messages
    const activeMessage = messages.value.find(
      message => message.run_id && ['pending', 'generating'].includes(message.state),
    )
    if (activeMessage && !sending.value)
      void resume(activeMessage)
  }

  async function selectConversation(targetId: string): Promise<void> {
    if (sending.value || targetId === conversationId.value)
      return
    conversationId.value = targetId
    loading.value = true
    error.value = ''
    try {
      await loadConversation(targetId)
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '会话加载失败'
    }
    finally {
      loading.value = false
    }
  }

  async function newConversation(): Promise<ConversationRow | null> {
    if (!knowledgeBaseId.value || sending.value)
      return null
    error.value = ''
    try {
      const conversation = await createConversation(knowledgeBaseId.value)
      conversations.value = [conversation, ...conversations.value]
      conversationId.value = conversation.id
      messages.value = []
      return conversation
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '会话创建失败'
      return null
    }
  }

  function applyStreamEvent(event: SseMessage, assistantMessageId: string): void {
    if (event.event === 'token') {
      const text = typeof event.data.text === 'string' ? event.data.text : ''
      const message = messages.value.find(item => item.id === assistantMessageId)
      if (message) {
        message.content += text
        message.state = 'generating'
      }
    }
    if (event.event === 'error') {
      error.value = typeof event.data.message === 'string'
        ? event.data.message
        : '问答生成失败，可以重试。'
    }
  }

  async function followRun(run: GenerationRun): Promise<void> {
    currentRun.value = run
    streamController = new AbortController()
    try {
      await streamRun(
        run.id,
        event => applyStreamEvent(event, run.assistant_message_id),
        streamController.signal,
      )
    }
    catch (cause) {
      if (!(cause instanceof DOMException && cause.name === 'AbortError'))
        error.value = cause instanceof Error ? cause.message : '流式连接已断开'
      currentRun.value = await fetchRun(run.id).catch(() => run)
    }
    finally {
      streamController = null
      await loadConversation().catch(() => undefined)
      await refreshConversationList().catch(() => undefined)
      sending.value = false
    }
  }

  async function refreshConversationList(): Promise<void> {
    if (!knowledgeBaseId.value)
      return
    conversations.value = (await fetchConversations(knowledgeBaseId.value)).items
  }

  async function sendQuestion(): Promise<void> {
    const text = question.value.trim()
    if (!text || sending.value)
      return
    error.value = ''
    try {
      let targetConversationId = conversationId.value
      if (!targetConversationId) {
        const conversation = await newConversation()
        if (!conversation)
          return
        targetConversationId = conversation.id
      }
      sending.value = true
      const run = await createRun(targetConversationId, text, requestId())
      question.value = ''
      await loadConversation(targetConversationId)
      await followRun(run)
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '问题发送失败'
      sending.value = false
    }
  }

  async function stopGeneration(): Promise<void> {
    const run = currentRun.value
    if (!run || !['queued', 'running'].includes(run.state))
      return
    try {
      currentRun.value = await cancelRun(run.id)
    }
    finally {
      streamController?.abort()
      await loadConversation().catch(() => undefined)
      sending.value = false
    }
  }

  async function retry(message: ChatMessageRow): Promise<void> {
    if (!message.run_id || sending.value)
      return
    sending.value = true
    error.value = ''
    try {
      const run = await retryRun(message.run_id, requestId())
      await loadConversation()
      await followRun(run)
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '重新生成失败'
      sending.value = false
    }
  }

  async function resume(message: ChatMessageRow): Promise<void> {
    if (!message.run_id || sending.value)
      return
    sending.value = true
    error.value = ''
    try {
      const run = await fetchRun(message.run_id)
      if (['queued', 'running'].includes(run.state))
        await followRun(run)
      else
        await loadConversation()
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '运行状态恢复失败'
      sending.value = false
    }
  }

  function showCitations(citations: Citation[]): void {
    selectedCitations.value = citations
    citationPanelOpen.value = true
  }

  function closeCitations(): void {
    citationPanelOpen.value = false
  }

  async function feedback(message: ChatMessageRow, rating: 'helpful' | 'not_helpful'): Promise<void> {
    await saveMessageFeedback(message.id, rating)
    message.feedback_rating = rating
  }

  watch(() => auth.activeSpaceId, async () => {
    conversationId.value = ''
    await loadKnowledgeBases()
  }, { immediate: true })

  watch(knowledgeBaseId, loadConversations, { immediate: true })

  onUnmounted(() => streamController?.abort())

  return {
    knowledgeBases,
    knowledgeBaseId,
    selectedKnowledgeBase,
    conversations,
    conversationId,
    selectedConversation,
    messages,
    question,
    currentRun,
    loading,
    sending,
    canSend,
    error,
    citationPanelOpen,
    selectedCitations,
    loadConversations,
    selectConversation,
    newConversation,
    sendQuestion,
    stopGeneration,
    retry,
    resume,
    showCitations,
    closeCitations,
    feedback,
  }
}
