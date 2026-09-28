// @vitest-environment happy-dom

/** 验证会话列表只展示公开元信息，并将非当前会话撤销意图回传给容器。 */
import type { AuthSession } from '@/api/auth'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SessionList from './index.vue'

const sessions: AuthSession[] = [
  {
    id: '31',
    created_at: '2026-09-20T00:00:00Z',
    last_seen_at: '2026-09-23T00:00:00Z',
    expires_at: '2026-09-23T12:00:00Z',
    is_current: true,
  },
  {
    id: '32',
    created_at: '2026-09-21T00:00:00Z',
    last_seen_at: '2026-09-22T00:00:00Z',
    expires_at: '2026-09-24T00:00:00Z',
    is_current: false,
  },
]

describe('session list', () => {
  it('marks the active browser session and only offers to revoke other sessions', async () => {
    const wrapper = mount(SessionList, {
      props: { items: sessions, loading: false, busyId: '' },
    })

    expect(wrapper.text()).toContain('当前会话')
    expect(wrapper.findAll('button')).toHaveLength(2)
    await wrapper.get('[aria-label="下线会话 32"]').trigger('click')
    expect(wrapper.emitted('revoke')).toEqual([[sessions[1]]])
    wrapper.unmount()
  })

  it('shows a loading state without hiding existing rows during refresh', () => {
    const wrapper = mount(SessionList, {
      props: { items: [sessions[1]!], loading: true, busyId: '' },
    })

    expect(wrapper.text()).toContain('会话 #32')
    expect(wrapper.text()).not.toContain('正在加载会话')
    wrapper.unmount()
  })
})
