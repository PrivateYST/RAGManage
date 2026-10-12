// @vitest-environment happy-dom
/** 环境检查迁移回归：保证健康状态、失败重试、刷新并发和卸载取消都有反馈。 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EnvironmentPage from './index.vue'

const api = vi.hoisted(() => ({
  fetchHealth: vi.fn(),
  toastError: vi.fn(),
}))

vi.mock('@/api/health', () => ({ fetchHealth: api.fetchHealth }))
vi.mock('@/composables/useToast', () => ({ useAppToast: () => ({ error: api.toastError }) }))

/** 提供可预测的基础服务状态，覆盖命名映射和就绪提示。 */
function readyHealth() {
  return { status: 'ready' as const, checks: { database: 'ok', redis: 'ok' } }
}

describe('environment page migration', () => {
  beforeEach(() => {
    api.fetchHealth.mockReset()
    api.toastError.mockReset()
  })

  it('loads and renders dependency health with translated labels', async () => {
    api.fetchHealth.mockResolvedValueOnce(readyHealth())
    const wrapper = mount(EnvironmentPage)

    await flushPromises()

    expect(api.fetchHealth).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('基础服务已就绪')
    expect(wrapper.text()).toContain('PostgreSQL / pgvector')
    expect(wrapper.text()).toContain('Redis')
    expect(wrapper.text()).toContain('正常')
    wrapper.unmount()
  })

  it('keeps a readable error and recovers after a manual retry', async () => {
    api.fetchHealth.mockRejectedValueOnce(new Error('network unavailable'))
    api.fetchHealth.mockResolvedValueOnce(readyHealth())
    const wrapper = mount(EnvironmentPage)

    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('请确认后端服务已启动')
    expect(api.toastError).toHaveBeenCalledWith(
      '服务状态检查失败',
      '请检查后端服务是否启动后重试。',
    )

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(api.fetchHealth).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('基础服务已就绪')
    wrapper.unmount()
  })

  it('aborts the active request when the page is unmounted', () => {
    api.fetchHealth.mockImplementationOnce(() => new Promise(() => undefined))
    const wrapper = mount(EnvironmentPage)
    const signal = api.fetchHealth.mock.calls[0]?.[0] as AbortSignal

    wrapper.unmount()

    expect(signal.aborted).toBe(true)
  })

  it('does not let an older aborted request clear the newer loading state', async () => {
    let resolveLatest: ((value: ReturnType<typeof readyHealth>) => void) | undefined
    api.fetchHealth
      .mockImplementationOnce((_signal: AbortSignal) => new Promise(() => undefined))
      .mockImplementationOnce(
        () => new Promise((resolve) => (resolveLatest = resolve as typeof resolveLatest)),
      )
    const wrapper = mount(EnvironmentPage)

    await wrapper.get('button').trigger('click')
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()

    resolveLatest?.(readyHealth())
    await flushPromises()

    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
    expect(wrapper.text()).toContain('基础服务已就绪')
    wrapper.unmount()
  })
})
