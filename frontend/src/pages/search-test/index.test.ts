// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, shallowRef } from 'vue'
import SearchTestPage from './index.vue'

const testState = vi.hoisted(() => ({
  search: vi.fn(),
}))

vi.mock('./index', () => ({
  useSearchTest: () => {
    const knowledgeBases = shallowRef([
      {
        id: '2',
        tenant_id: '1',
        name: '医院服务规则',
        description: '',
        purpose: 'rule',
        status: 'published',
        active_release_id: '5',
        document_count: 1,
        updated_at: '2026-09-17T00:00:00Z',
      },
    ])
    const knowledgeBaseId = shallowRef('2')
    return {
      knowledgeBases,
      knowledgeBaseId,
      selectedKnowledgeBase: computed(() => knowledgeBases.value[0]),
      query: shallowRef('出院结算需要什么材料？'),
      topK: shallowRef(10),
      contextMaxChars: shallowRef(6000),
      loadingKnowledgeBases: shallowRef(false),
      searching: shallowRef(false),
      canSearch: computed(() => true),
      error: shallowRef(''),
      result: shallowRef({
        trace_id: '31',
        state: 'completed',
        message: '已召回 1 条证据。',
        release: {
          id: '5',
          embedding_profile_id: '4',
          model_name: 'qwen3-embedding:0.6b',
          model_revision: 'revision',
          dimension: 1024,
          manifest_hash: 'manifest',
        },
        source_stats: {
          total_documents: 1,
          valid_documents: 1,
          invalid_documents: 0,
          valid_chunks: 10,
          embedded_chunks: 10,
        },
        filters: [{ name: '当前 Release', value: '5', filtered_count: 0 }],
        timings: { total_ms: 120, vector_search_ms: 4 },
        context: '[证据 1] 出院服务',
        items: [{
          chunk_id: '21',
          document_id: '13',
          document_title: '住院服务指南.md',
          document_version_id: '17',
          version_no: 2,
          content: '患者持出院通知单到结算窗口办理。',
          section_path: ['住院服务', '出院'],
          locator: { line_start: 18, line_end: 20 },
          similarity: 0.91,
          raw_rank: 1,
          rank: 1,
          context_included: true,
          evidence_no: 1,
        }],
      }),
      loadKnowledgeBases: vi.fn(),
      search: testState.search,
    }
  },
}))

describe('search test page', () => {
  beforeEach(() => testState.search.mockClear())

  it('runs retrieval through the query form', async () => {
    const wrapper = mount(SearchTestPage)

    await wrapper.get('form').trigger('submit')

    expect(testState.search).toHaveBeenCalledOnce()
  })

  it('shows release scope, evidence score and source locator', () => {
    const wrapper = mount(SearchTestPage)

    expect(wrapper.text()).toContain('Release #5')
    expect(wrapper.text()).toContain('住院服务指南.md')
    expect(wrapper.text()).toContain('91.0%')
    expect(wrapper.text()).toContain('第 18–20 行')
    expect(wrapper.text()).toContain('已进入上下文')
    expect(wrapper.text()).toContain('RRF 融合排序')
  })
})
