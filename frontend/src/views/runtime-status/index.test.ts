import type { RuntimeMetrics } from '@/api/health'
// @vitest-environment happy-dom
/** 运行状态迁移回归：防止拆分后丢失指标加载、手动刷新和请求取消行为。 */
import { flushPromises, mount } from '@vue/test-utils'

import { describe, expect, it, vi } from 'vitest'
import { routeComponents } from '@/router'
import { formatBytes } from './index'
import RuntimeStatusPage from './index.vue'

const api = vi.hoisted(() => ({ fetchRuntimeMetrics: vi.fn() }))

vi.mock('@/api/health', () => ({ fetchRuntimeMetrics: api.fetchRuntimeMetrics }))

/** 以最小完整的聚合响应验证三张卡片的展示边界。 */
function runtimeMetrics(): RuntimeMetrics {
  return {
    status: 'ok',
    database: 'ok',
    tasks: { queued: 2, running: 1, failed: 3 },
    models: { healthy: 4, unhealthy: 1, unknown: 2 },
    storage: { status: 'ok', used_bytes: 1024, free_bytes: 2048, total_bytes: 3072 },
  }
}

describe('runtime status migration', () => {
  it('keeps the dedicated route and formats optional byte metrics', () => {
    expect(routeComponents['/system/status']).toBeDefined()
    expect(routeComponents['/system/status']).not.toBe(routeComponents['/dashboard'])
    expect(formatBytes()).toBe('不可用')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(1024)).toBe('1.0 KiB')
  })

  it('loads aggregated metrics and renders the three feature cards', async () => {
    api.fetchRuntimeMetrics.mockResolvedValueOnce(runtimeMetrics())
    const wrapper = mount(RuntimeStatusPage)

    await flushPromises()

    expect(api.fetchRuntimeMetrics).toHaveBeenCalledOnce()
    expect(wrapper.text()).toContain('排队中')
    expect(wrapper.text()).toContain('模型端点')
    expect(wrapper.text()).toContain('3.0 KiB')
    wrapper.unmount()
  })

  it('shows a failed refresh and recovers when the user retries', async () => {
    api.fetchRuntimeMetrics
      .mockRejectedValueOnce(new Error('指标服务不可用'))
      .mockResolvedValueOnce(runtimeMetrics())
    const wrapper = mount(RuntimeStatusPage)

    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('指标服务不可用')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(api.fetchRuntimeMetrics).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('文件存储')
    wrapper.unmount()
  })

  it('aborts the in-flight request when the page is unmounted', () => {
    api.fetchRuntimeMetrics.mockImplementationOnce(
      (signal: AbortSignal) =>
        new Promise(() => {
          expect(signal.aborted).toBe(false)
        }),
    )
    const wrapper = mount(RuntimeStatusPage)
    const signal = api.fetchRuntimeMetrics.mock.calls.at(-1)?.[0] as AbortSignal

    wrapper.unmount()

    expect(signal.aborted).toBe(true)
  })
})
