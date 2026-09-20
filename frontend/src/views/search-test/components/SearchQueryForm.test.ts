// @vitest-environment happy-dom

import type { KnowledgeBaseRow } from '@/api/admin'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SearchQueryForm from './SearchQueryForm.vue'

const publishedKnowledgeBase: KnowledgeBaseRow = {
  id: '2',
  tenant_id: '1',
  name: '医院服务规则',
  description: '',
  purpose: 'rule',
  status: 'published',
  active_release_id: '5',
  document_count: 1,
  updated_at: '2026-09-17T00:00:00Z',
}

function mountForm(options: { query?: string; canSearch?: boolean; loading?: boolean } = {}) {
  return mount(SearchQueryForm, {
    props: {
      knowledgeBases: [publishedKnowledgeBase],
      knowledgeBaseId: '2',
      query: options.query ?? '',
      topK: 10,
      contextMaxChars: 6000,
      loading: options.loading ?? false,
      searching: false,
      canSearch: options.canSearch ?? false,
    },
  })
}

describe('search query form', () => {
  it('explains why retrieval is disabled when the question is empty', () => {
    const wrapper = mountForm()

    expect(wrapper.get('.search-run-button').attributes('disabled')).toBeDefined()
    expect(wrapper.get('.search-run-hint').text()).toBe('请输入测试问题后运行检索')
  })

  it('explains what an enabled retrieval action will do', () => {
    const wrapper = mountForm({ query: '出院结算需要携带哪些材料？', canSearch: true })

    expect(wrapper.get('.search-run-button').attributes('disabled')).toBeUndefined()
    expect(wrapper.get('.search-run-hint').text()).toBe(
      '将在当前 Release 中融合召回证据，不会生成回答',
    )
  })

  it('shows the loading reason while knowledge bases are refreshing', () => {
    const wrapper = mountForm({ loading: true })

    expect(wrapper.get('.search-run-hint').text()).toBe('正在加载知识库和发布版本…')
  })
})
