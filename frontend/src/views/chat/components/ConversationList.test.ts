// @vitest-environment happy-dom

/** 会话列表交互回归：确认删除前不发事件，确认后向父级发出会话 ID。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationList from './ConversationList.vue'

const conversation = {
  id: 'conversation-1',
  tenant_id: 'tenant-1',
  knowledge_base_id: 'knowledge-base-1',
  title: '出院办理',
  status: 'active',
  message_count: 2,
  created_at: '2026-09-18T00:00:00Z',
  updated_at: '2026-09-18T00:00:00Z',
}

describe('conversation list', () => {
  it('confirms before emitting a delete request', async () => {
    const wrapper = mount(ConversationList, {
      props: { conversations: [conversation], activeId: conversation.id, disabled: false },
    })

    expect(wrapper.emitted('delete')).toBeUndefined()
    await wrapper.get('[aria-label="删除会话：出院办理"]').trigger('click')
    expect(wrapper.emitted('delete')).toBeUndefined()

    const dialog = document.body.querySelector('[role="alertdialog"]')
    expect(dialog).not.toBeNull()
    const confirmButton = dialog?.querySelector('button:last-child') as HTMLButtonElement
    confirmButton.click()
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('delete')).toEqual([[conversation.id]])
    expect(wrapper.get('.min-h-0.overflow-y-auto').classes()).toContain('overscroll-contain')
    wrapper.unmount()
  })
})
