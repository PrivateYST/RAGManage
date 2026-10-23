// @vitest-environment happy-dom
/** 单条快捷操作回归：检查每种状态都只发出对应的一次状态迁移。 */
import type { WikiEntry, WikiStatus } from '@/api/wiki'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WikiEntryList from './index.vue'

/** 构造只包含列表渲染所需字段的词条，状态由各用例覆盖。 */
function makeEntry(status: WikiStatus): WikiEntry {
  return {
    id: '1',
    knowledge_base_id: '9',
    term: '儿童健康',
    definition: '规范定义',
    status,
    version_no: 2,
    owner_user_id: '7',
    valid_from: null,
    valid_until: null,
    aliases: [],
    sources: [],
    updated_at: '2026-10-16T00:00:00Z',
  }
}

describe('wiki entry list single-entry actions', () => {
  it.each([
    { from: 'draft', label: '审核并发布', to: 'published' },
    { from: 'review', label: '审核并发布', to: 'published' },
    { from: 'published', label: '停用', to: 'retired' },
    { from: 'retired', label: '启用', to: 'published' },
  ] as const)('$from can $label in one action', async ({ from, label, to }) => {
    const entry = makeEntry(from)
    const wrapper = mount(WikiEntryList, {
      props: { entries: [entry], canManage: true, busy: false },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })

    const actionButton = wrapper.findAll('button').find((button) => button.text() === label)
    expect(actionButton).toBeDefined()
    await actionButton!.trigger('click')

    expect(wrapper.emitted('transition')).toEqual([[entry, to]])
  })
})
