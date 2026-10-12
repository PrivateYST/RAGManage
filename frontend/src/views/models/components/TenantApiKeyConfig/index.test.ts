// @vitest-environment happy-dom
/** 医院 Key 交接回归：验证按空间重载、粘贴核验、失败重试及成功后清除明文。 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TenantApiKeyConfig from './index.vue'

const mocks = vi.hoisted(() => ({
  fetchConfiguration: vi.fn(),
  confirmConfiguration: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))

vi.mock('@/api/tenantApiKeys', () => ({
  fetchTenantApiKeyConfiguration: mocks.fetchConfiguration,
  confirmTenantApiKeyConfiguration: mocks.confirmConfiguration,
}))

vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: mocks.success, error: mocks.error }),
}))

const assignedKey = {
  configured: false,
  key_prefix: 'sk-abcdefgh…wxyz',
  status: 'active' as const,
  configured_at: null,
}

describe('tenant api key configuration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetchConfiguration.mockResolvedValue(assignedKey)
  })

  it('confirms the current space key and clears plaintext after success', async () => {
    mocks.confirmConfiguration.mockResolvedValue({
      ...assignedKey,
      configured: true,
      configured_at: '2026-10-12T00:00:00Z',
    })
    const wrapper = mount(TenantApiKeyConfig, {
      props: { tenantId: '3', tenantName: '测试医院' },
    })
    await flushPromises()

    await wrapper.get('input').setValue('  sk-current-hospital-secret  ')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.confirmConfiguration).toHaveBeenCalledWith('3', 'sk-current-hospital-secret')
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('已确认配置')
    expect(wrapper.text()).not.toContain('sk-current-hospital-secret')
    expect(mocks.success).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('keeps the input for correction after a mismatch and allows retry', async () => {
    mocks.confirmConfiguration
      .mockRejectedValueOnce(new Error('此 Key 与系统分配的最新 Key 不匹配'))
      .mockResolvedValueOnce({ ...assignedKey, configured: true })
    const wrapper = mount(TenantApiKeyConfig, {
      props: { tenantId: '3', tenantName: '测试医院' },
    })
    await flushPromises()
    await wrapper.get('input').setValue('sk-wrong-key')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('不匹配')
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('sk-wrong-key')
    await wrapper.get('input').setValue('sk-current-hospital-secret')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(mocks.confirmConfiguration).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('已确认配置')
    expect((wrapper.get('input').element as HTMLInputElement).value).toBe('')
    wrapper.unmount()
  })

  it('reloads a switched hospital and discards the previous hospital input', async () => {
    const wrapper = mount(TenantApiKeyConfig, {
      props: { tenantId: '3', tenantName: '测试医院' },
    })
    await flushPromises()
    await wrapper.get('input').setValue('sk-unsubmitted-key')
    mocks.fetchConfiguration.mockResolvedValueOnce({
      configured: false,
      key_prefix: null,
      status: null,
      configured_at: null,
    })
    await wrapper.setProps({ tenantId: '4', tenantName: '内部医院' })
    await flushPromises()

    expect(mocks.fetchConfiguration).toHaveBeenLastCalledWith('4')
    expect(wrapper.text()).toContain('尚未分配医院 Key')
    expect(wrapper.text()).not.toContain('sk-unsubmitted-key')
    wrapper.unmount()
  })
})
