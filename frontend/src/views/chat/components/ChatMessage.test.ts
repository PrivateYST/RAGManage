// @vitest-environment happy-dom

import type { ChatMessageRow } from '@/api/chat'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatMessage from './ChatMessage.vue'

function assistantMessage(overrides: Partial<ChatMessageRow> = {}): ChatMessageRow {
  return {
    id: '22',
    role: 'assistant',
    content: '当前知识库索引尚未就绪，暂时无法回答。',
    state: 'complete',
    release_id: null,
    created_at: '2026-09-18T00:00:00Z',
    run_id: '41',
    outcome: 'index_not_ready',
    hidden: false,
    citations: [],
    feedback_rating: null,
    feedback_reason: null,
    ...overrides,
  }
}

describe('chat message', () => {
  it('shows an explicit refusal outcome and allows feedback on completed responses', () => {
    const wrapper = mount(ChatMessage, {
      props: { message: assistantMessage(), busy: false },
    })

    expect(wrapper.get('.chat-outcome').text()).toBe('索引未就绪')
    expect(wrapper.find('[aria-label="回答有帮助"]').exists()).toBe(true)
    expect(wrapper.find('[aria-label="回答没有帮助"]').exists()).toBe(true)
  })

  it('shows retry without feedback for a cancelled response', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        message: assistantMessage({ content: '', state: 'cancelled', outcome: null }),
        busy: false,
      },
    })

    expect(wrapper.text()).toContain('已停止')
    expect(wrapper.text()).toContain('重新生成')
    expect(wrapper.find('.chat-feedback-actions').exists()).toBe(false)
  })

  it('hides revoked-source content and all response actions', () => {
    const wrapper = mount(ChatMessage, {
      props: {
        message: assistantMessage({ content: '', state: 'hidden', hidden: true }),
        busy: false,
      },
    })

    expect(wrapper.text()).toContain('来源权限已失效，回答已隐藏')
    expect(wrapper.find('.chat-feedback-actions').exists()).toBe(false)
    expect(wrapper.find('footer button').exists()).toBe(false)
  })
})
