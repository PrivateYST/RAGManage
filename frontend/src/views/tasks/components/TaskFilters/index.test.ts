// @vitest-environment happy-dom
/** 筛选子视图回归：确认受控选择器只上报值，不绕过页面自行请求数据。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import TaskFilters from './index.vue'

describe('task filters', () => {
  it('emits selected knowledge base and state values to its owner', async () => {
    const wrapper = mount(TaskFilters, {
      props: {
        knowledgeBases: [
          {
            id: 'kb-1',
            tenant_id: 'space-1',
            name: '临床知识库',
            description: '',
            purpose: 'general',
            status: 'active',
            active_release_id: null,
            document_count: 0,
            updated_at: '2026-01-01T00:00:00Z',
          },
        ],
        knowledgeBaseId: 'all',
        stateFilter: 'all',
        visibleTaskCount: 3,
      },
    })

    await wrapper.findAll('select')[0]!.setValue('kb-1')
    await wrapper.findAll('select')[1]!.setValue('failed')

    expect(wrapper.emitted('update:knowledgeBaseId')?.[0]).toEqual(['kb-1'])
    expect(wrapper.emitted('update:stateFilter')?.[0]).toEqual(['failed'])
    expect(wrapper.text()).toContain('共 3 个任务')
  })
})
