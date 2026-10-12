// @vitest-environment happy-dom

/** 对话页逻辑回归：验证空间/知识库会话范围、流式回答和失败恢复反馈。 */
import type { ChatMessageRow, ConversationRow, GenerationRun } from '@/api/chat'
import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'

import { useChatRun } from './index'

const api = vi.hoisted(() => ({
  auth: { activeSpaceId: '' },
  fetchKnowledgeBases: vi.fn(),
  fetchConversations: vi.fn(),
  fetchConversation: vi.fn(),
  createConversation: vi.fn(),
  createRun: vi.fn(),
  streamRun: vi.fn(),
  fetchRun: vi.fn(),
  cancelRun: vi.fn(),
  retryRun: vi.fn(),
  deleteConversation: vi.fn(),
  feedback: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
  toastInfo: vi.fn(),
}))

vi.mock('@/api/admin', () => ({ fetchKnowledgeBases: api.fetchKnowledgeBases }))
vi.mock('@/api/chat', () => ({
  cancelRun: api.cancelRun,
  createConversation: api.createConversation,
  createRun: api.createRun,
  deleteConversation: api.deleteConversation,
  fetchConversation: api.fetchConversation,
  fetchConversations: api.fetchConversations,
  fetchRun: api.fetchRun,
  retryRun: api.retryRun,
  saveMessageFeedback: api.feedback,
  streamRun: api.streamRun,
}))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({
    error: api.toastError,
    success: api.toastSuccess,
    info: api.toastInfo,
  }),
}))
vi.mock('@/store/auth', () => ({ useAuthStore: () => api.auth }))

const conversation: ConversationRow = {
  id: 'conversation-1',
  tenant_id: 'space-1',
  knowledge_base_id: 'kb-1',
  title: '新会话',
  status: 'active',
  message_count: 0,
  created_at: '2026-09-18T00:00:00Z',
  updated_at: '2026-09-18T00:00:00Z',
}

/** 为流式回归构造服务端消息，避免测试依赖页面模板内的隐式数据。 */
function assistantMessage(state: string, content: string): ChatMessageRow {
  return {
    id: 'assistant-1',
    role: 'assistant',
    content,
    state,
    release_id: 'release-1',
    created_at: '2026-09-18T00:00:01Z',
    run_id: 'run-1',
    run_state: state === 'pending' ? 'running' : 'completed',
    outcome: state === 'complete' ? 'answered' : null,
    hidden: false,
    citations: [],
    feedback_rating: null,
    feedback_reason: null,
  }
}

/** 创建作用域隔离的页面逻辑实例，卸载时同时清理知识库监听。 */
function createPage() {
  const scope = effectScope()
  const page = scope.run(() => useChatRun())
  if (!page) throw new Error('问答页面逻辑作用域未能启动')
  return { page, dispose: () => scope.stop() }
}

describe('chat page logic', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    api.auth = reactive({ activeSpaceId: 'space-1' })
    api.fetchKnowledgeBases.mockResolvedValue({
      items: [
        {
          id: 'kb-1',
          tenant_id: 'space-1',
          name: '医院服务规则',
          description: '',
          purpose: 'rule',
          status: 'published',
          active_release_id: 'release-1',
          document_count: 1,
          updated_at: '2026-09-18T00:00:00Z',
        },
      ],
    })
    api.fetchConversations.mockResolvedValue({ items: [] })
    api.createConversation.mockResolvedValue(conversation)
  })

  it('sends a trimmed question in the active knowledge base and applies streamed content', async () => {
    api.createRun.mockResolvedValue({
      id: 'run-1',
      tenant_id: 'space-1',
      knowledge_base_id: 'kb-1',
      conversation_id: 'conversation-1',
      user_message_id: 'user-1',
      assistant_message_id: 'assistant-1',
      release_id: 'release-1',
      request_id: 'request-1',
      state: 'running',
      outcome: null,
      cancel_requested: false,
      error: null,
      created_at: '2026-09-18T00:00:00Z',
      updated_at: '2026-09-18T00:00:00Z',
    } satisfies GenerationRun)
    api.fetchConversation
      .mockResolvedValueOnce({ conversation, messages: [assistantMessage('pending', '')] })
      .mockResolvedValueOnce({ conversation, messages: [assistantMessage('complete', '已回答。')] })
    api.streamRun.mockImplementation(async (_runId, onEvent) => {
      onEvent({ event: 'token', data: { text: '已回答。' } })
    })
    const { page, dispose } = createPage()
    await flushPromises()
    page.question.value = '  出院结算需要什么材料？  '

    await page.sendQuestion()

    expect(api.fetchKnowledgeBases).toHaveBeenCalledWith('space-1')
    expect(api.fetchConversations).toHaveBeenCalledWith('kb-1')
    expect(api.createConversation).toHaveBeenCalledWith('kb-1')
    expect(api.createRun).toHaveBeenCalledWith(
      'conversation-1',
      '出院结算需要什么材料？',
      expect.any(String),
    )
    expect(api.streamRun).toHaveBeenCalledWith(
      'run-1',
      expect.any(Function),
      expect.any(AbortSignal),
    )
    expect(page.question.value).toBe('')
    expect(page.messages.value[0]?.content).toBe('已回答。')
    expect(page.sending.value).toBe(false)
    dispose()
  })

  it('keeps an actionable page error when knowledge-base loading fails', async () => {
    api.fetchKnowledgeBases.mockRejectedValue(new Error('知识库暂不可用'))
    const { page, dispose } = createPage()

    await flushPromises()

    expect(page.loadError.value).toBe('知识库暂不可用')
    expect(page.knowledgeBases.value).toEqual([])
    expect(api.toastError).toHaveBeenCalledWith('知识库暂不可用')
    dispose()
  })
})
