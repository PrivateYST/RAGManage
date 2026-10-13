// @vitest-environment happy-dom
/** 空间管理员 Key 配置弹窗回归：保证表单位于可关闭的模态框中。 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppDialog from '@/components/AppDialog/index.vue'
import TenantApiKeyDialog from './index.vue'

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

describe('tenant api key dialog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.fetchConfiguration.mockResolvedValue({
      configured: false,
      key_prefix: 'sk-abcdefgh…wxyz',
      status: 'active',
      configured_at: null,
    })
    mocks.confirmConfiguration.mockResolvedValue({
      configured: true,
      key_prefix: 'sk-abcdefgh…wxyz',
      status: 'active',
      configured_at: '2026-10-13T00:00:00Z',
    })
  })

  it('shows the existing handoff form in a closable modal', async () => {
    const wrapper = mount(TenantApiKeyDialog, {
      props: { open: true, tenantId: '3', tenantName: '测试医院' },
    })
    await flushPromises()

    expect(wrapper.getComponent(AppDialog).props('open')).toBe(true)
    expect(document.body.textContent).toContain('医院 API Key 配置')
    expect(document.body.textContent).toContain('测试医院')

    const input = document.body.querySelector<HTMLInputElement>('#tenant-api-key-input')
    const form = document.body.querySelector<HTMLFormElement>('form')
    expect(input).toBeTruthy()
    expect(form).toBeTruthy()
    input!.value = 'sk-current-key'
    input!.dispatchEvent(new Event('input', { bubbles: true }))
    form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(mocks.confirmConfiguration).toHaveBeenCalledWith('3', 'sk-current-key')
    expect(wrapper.emitted('configured')).toHaveLength(1)

    wrapper.getComponent(AppDialog).vm.$emit('close')
    await wrapper.vm.$nextTick()
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })
})
