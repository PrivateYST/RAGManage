// @vitest-environment happy-dom

import type { SpaceMember } from '../../../../api/members'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MemberTable from './index.vue'

const member: SpaceMember = {
  id: '8',
  login: 'editor-a',
  display_name: '编辑甲',
  user_status: 'active',
  status: 'active',
  role_code: 'space_member',
  knowledge_base_count: 1,
  created_at: '2026-09-19T00:00:00Z',
}

describe('member table', () => {
  it('emits role and status operations for a real member row', async () => {
    const wrapper = mount(MemberTable, {
      props: { items: [member], loading: false, busyId: '' },
    })

    await wrapper.get('select').setValue('space_admin')
    await wrapper.get('button').trigger('click')

    expect(wrapper.emitted('changeRole')?.[0]).toEqual([member, 'space_admin'])
    expect(wrapper.emitted('toggleStatus')?.[0]).toEqual([member])
    expect(wrapper.text()).toContain('1 个显式授权')
  })

  it('disables role editing while the member is stopped', () => {
    const wrapper = mount(MemberTable, {
      props: {
        items: [{ ...member, status: 'disabled' }],
        loading: false,
        busyId: '',
      },
    })

    expect(wrapper.get('select').attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('已停用')
    expect(wrapper.get('button').text()).toContain('恢复')
  })
})
