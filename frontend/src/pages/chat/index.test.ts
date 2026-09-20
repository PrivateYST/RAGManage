// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, ref, shallowRef } from 'vue'
import ChatPage from './index.vue'

const testState = vi.hoisted(() => ({
  sendQuestion: vi.fn(),
}))

vi.mock('./index', () => ({
  useChatRun: () => {
    const knowledgeBases = ref([{
      id: '2',
      tenant_id: '1',
      name: '医院服务规则',
      description: '',
      purpose: 'rule',
      status: 'published',
      active_release_id: '5',
      document_count: 1,
      updated_at: '2026-09-18T00:00:00Z',
    }])
    const conversations = ref([{
      id: '10',
      tenant_id: '1',
      knowledge_base_id: '2',
      title: '出院办理',
      status: 'active',
      message_count: 2,
      created_at: '2026-09-18T00:00:00Z',
      updated_at: '2026-09-18T00:00:00Z',
    }])
    return {
      knowledgeBases,
      knowledgeBaseId: shallowRef('2'),
      selectedKnowledgeBase: computed(() => knowledgeBases.value[0]),
      conversations,
      conversationId: shallowRef('10'),
      selectedConversation: computed(() => conversations.value[0]),
      messages: ref([{
        id: '21',
        role: 'user',
        content: '如何办理出院？',
        state: 'complete',
        release_id: '5',
        created_at: '2026-09-18T00:00:00Z',
        run_id: null,
        hidden: false,
        citations: [],
        feedback_rating: null,
        feedback_reason: null,
      }, {
        id: '22',
        role: 'assistant',
        content: '请持出院通知单办理结算。[证据 1]',
        state: 'complete',
        release_id: '5',
        created_at: '2026-09-18T00:00:01Z',
        run_id: '41',
        hidden: false,
        citations: [{
          evidence_no: 1,
          chunk_id: '31',
          document_id: '13',
          document_title: '住院服务指南.md',
          document_version_id: '17',
          version_no: 2,
          locator: { line_start: 18, line_end: 20 },
          section_path: ['住院服务', '出院'],
          content: '患者持出院通知单办理。',
          source_path: '/documents?document_id=13',
        }],
        feedback_rating: null,
        feedback_reason: null,
      }]),
      question: shallowRef('新的问题'),
      currentRun: shallowRef(null),
      loading: shallowRef(false),
      sending: shallowRef(false),
      canSend: computed(() => true),
      error: shallowRef(''),
      citationPanelOpen: shallowRef(true),
      selectedCitations: ref([{
        evidence_no: 1,
        chunk_id: '31',
        document_id: '13',
        document_title: '住院服务指南.md',
        document_version_id: '17',
        version_no: 2,
        locator: { line_start: 18, line_end: 20 },
        section_path: ['住院服务', '出院'],
        content: '患者持出院通知单办理。',
        source_path: '/documents?document_id=13',
      }]),
      selectConversation: vi.fn(),
      newConversation: vi.fn(),
      sendQuestion: testState.sendQuestion,
      stopGeneration: vi.fn(),
      retry: vi.fn(),
      resume: vi.fn(),
      showCitations: vi.fn(),
      closeCitations: vi.fn(),
      feedback: vi.fn(),
    }
  },
}))

describe('chat page', () => {
  beforeEach(() => testState.sendQuestion.mockClear())

  it('submits a question through the real composer', async () => {
    const wrapper = mount(ChatPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })

    await wrapper.get('.chat-composer').trigger('submit')

    expect(testState.sendQuestion).toHaveBeenCalledOnce()
  })

  it('shows validated answer citations and source position', () => {
    const wrapper = mount(ChatPage, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })

    expect(wrapper.text()).toContain('请持出院通知单办理结算。[证据 1]')
    expect(wrapper.text()).toContain('住院服务指南.md')
    expect(wrapper.text()).toContain('第 18–20 行')
  })
})
