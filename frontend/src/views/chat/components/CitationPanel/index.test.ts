// @vitest-environment happy-dom

/** 引用面板回归：引用展示服务端定位，并将关闭意图交回工作区。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CitationPanel from './index.vue'

describe('citation panel', () => {
  it('shows the verified source location and emits close', async () => {
    const wrapper = mount(CitationPanel, {
      props: {
        open: true,
        citations: [
          {
            evidence_no: 1,
            chunk_id: 'chunk-1',
            document_id: 'document-1',
            document_title: '住院服务指南.md',
            document_version_id: 'version-1',
            version_no: 2,
            locator: { line_start: 18, line_end: 20 },
            section_path: ['住院服务', '出院'],
            content: '持出院通知单办理结算。',
            source_path: '/documents?document_id=document-1',
            wiki_entries: [{ id: '1', term: '出院结算', version_no: 3 }],
          },
        ],
      },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    expect(wrapper.text()).toContain('住院服务指南.md')
    expect(wrapper.text()).toContain('第 18–20 行')
    expect(wrapper.text()).toContain('出院结算 · v3（已发布）')
    await wrapper.get('[aria-label="关闭引用"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
