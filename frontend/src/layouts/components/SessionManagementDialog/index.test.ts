// @vitest-environment happy-dom

/** 会话管理闭环回归：加载失败可重试，撤销必须确认，成功后更新列表并反馈。 */
import type { AuthSession } from '@/api/auth'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SessionManagementDialog from './index.vue'

const apiMocks = vi.hoisted(() => ({ listSessions: vi.fn(), revokeSession: vi.fn() }))
const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))

vi.mock('@/api/auth', () => ({
  listSessions: apiMocks.listSessions,
  revokeSession: apiMocks.revokeSession,
}))
vi.mock('@/composables/useToast', () => ({ useAppToast: () => toastMocks }))

const currentSession: AuthSession = {
  id: '31',
  created_at: '2026-09-20T00:00:00Z',
  last_seen_at: '2026-09-23T00:00:00Z',
  expires_at: '2026-09-23T12:00:00Z',
  is_current: true,
}
const otherSession: AuthSession = {
  ...currentSession,
  id: '32',
  is_current: false,
}

describe('session management dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listSessions.mockResolvedValue({ items: [currentSession, otherSession] })
    apiMocks.revokeSession.mockResolvedValue(undefined)
  })

  it('loads the latest sessions when opened and refreshes after reopening', async () => {
    const wrapper = mount(SessionManagementDialog, { props: { open: true } })
    await flushPromises()

    expect(apiMocks.listSessions).toHaveBeenCalledOnce()
    expect(document.body.textContent).toContain('会话 #31')
    expect(document.body.textContent).toContain('会话 #32')

    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(apiMocks.listSessions).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('keeps the session until confirmation, then revokes it and reports success', async () => {
    const wrapper = mount(SessionManagementDialog, { props: { open: true } })
    await flushPromises()

    document.body.querySelector<HTMLButtonElement>('[aria-label="下线会话 32"]')?.click()
    await flushPromises()
    expect(apiMocks.revokeSession).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('确认下线会话 #32')

    const confirm = Array.from(
      document.body.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button'),
    ).find((button) => button.textContent?.includes('确认下线'))
    confirm?.click()
    await flushPromises()

    expect(apiMocks.revokeSession).toHaveBeenCalledWith('32')
    expect(document.body.textContent).not.toContain('会话 #32')
    expect(toastMocks.success).toHaveBeenCalledWith('登录会话已下线')
    wrapper.unmount()
  })

  it('shows a retry action when loading fails and recovers from a later success', async () => {
    apiMocks.listSessions
      .mockRejectedValueOnce(new Error('服务暂不可用'))
      .mockResolvedValueOnce({ items: [currentSession] })
    const wrapper = mount(SessionManagementDialog, { props: { open: true } })
    await flushPromises()

    expect(document.body.textContent).toContain('服务暂不可用')
    document.body.querySelector<HTMLButtonElement>('[role="alert"] button')?.click()
    await flushPromises()

    expect(apiMocks.listSessions).toHaveBeenCalledTimes(2)
    expect(document.body.textContent).toContain('会话 #31')
    expect(document.body.textContent).not.toContain('服务暂不可用')
    wrapper.unmount()
  })

  it('logs out this browser after the user confirms revoking the current session', async () => {
    const wrapper = mount(SessionManagementDialog, { props: { open: true } })
    await flushPromises()

    document.body.querySelector<HTMLButtonElement>('[aria-label="退出当前会话 31"]')?.click()
    await flushPromises()
    expect(document.body.textContent).toContain('下线后当前浏览器会立即退出登录。')

    Array.from(document.body.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button'))
      .find((button) => button.textContent?.includes('确认下线'))
      ?.click()
    await flushPromises()

    expect(apiMocks.revokeSession).toHaveBeenCalledWith('31')
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.emitted('current-session-revoked')).toHaveLength(1)
    wrapper.unmount()
  })

  it('keeps the session and reports an error when revocation fails', async () => {
    apiMocks.revokeSession.mockRejectedValueOnce(new Error('会话已失效'))
    const wrapper = mount(SessionManagementDialog, { props: { open: true } })
    await flushPromises()

    document.body.querySelector<HTMLButtonElement>('[aria-label="下线会话 32"]')?.click()
    await flushPromises()
    Array.from(document.body.querySelectorAll<HTMLButtonElement>('[role="alertdialog"] button'))
      .find((button) => button.textContent?.includes('确认下线'))
      ?.click()
    await flushPromises()

    expect(document.body.textContent).toContain('会话 #32')
    expect(toastMocks.error).toHaveBeenCalledWith('会话已失效')
    wrapper.unmount()
  })
})
