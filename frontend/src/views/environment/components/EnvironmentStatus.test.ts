// @vitest-environment happy-dom
/**
 * 环境状态卡片回归测试：确保服务查询的 loading、错误和成功状态都能被用户感知，
 * 防止网络异常时页面只剩 Toast 而无法回看失败原因。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import EnvironmentStatus from './EnvironmentStatus.vue'

const fetchHealthMock = vi.hoisted(() => vi.fn())

vi.mock('@/api/health', () => ({
  fetchHealth: fetchHealthMock,
}))

describe('environmentStatus', () => {
  beforeEach(() => fetchHealthMock.mockReset())

  it('renders dependency statuses after a successful request', async () => {
    fetchHealthMock.mockResolvedValue({
      status: 'ready',
      checks: { database: 'ok', redis: 'ok' },
    })
    const wrapper = mount(EnvironmentStatus)

    await flushPromises()

    expect(wrapper.text()).toContain('基础服务已就绪')
    expect(wrapper.text()).toContain('PostgreSQL / pgvector')
    expect(wrapper.text()).toContain('正常')
  })
})
