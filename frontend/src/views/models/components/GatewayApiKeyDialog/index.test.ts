// @vitest-environment happy-dom
/**
 * 全局网关 Key 弹窗无障碍回归：覆盖空输入错误关联和异步保存中的忙碌播报，
 * 防止敏感凭据配置出现不可定位的错误或重复提交。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import GatewayApiKeyDialog from './index.vue'

const apiMocks = vi.hoisted(() => ({
  fetchModelGatewayKey: vi.fn(),
  updateModelGatewayKey: vi.fn(),
}))

vi.mock('@/api/models', () => ({
  fetchModelGatewayKey: apiMocks.fetchModelGatewayKey,
  updateModelGatewayKey: apiMocks.updateModelGatewayKey,
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve
  })
  return { promise, resolve }
}

describe('gateway api key dialog', () => {
  it('associates empty-key feedback with the sensitive input', async () => {
    apiMocks.fetchModelGatewayKey.mockResolvedValue({
      configured: false,
      source: 'environment',
      masked: '',
    })
    const wrapper = mount(GatewayApiKeyDialog, { props: { open: true } })
    await flushPromises()

    const form = document.body.querySelector('.gateway-key-form') as HTMLFormElement
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await wrapper.vm.$nextTick()

    const input = document.body.querySelector('.gateway-key-form input') as HTMLInputElement
    const error = document.body.querySelector('#gateway-key-form-error') as HTMLElement
    expect(error.getAttribute('role')).toBe('alert')
    expect(error.getAttribute('aria-live')).toBe('polite')
    expect(input.getAttribute('aria-invalid')).toBe('true')
    expect(input.getAttribute('aria-describedby')).toBe('gateway-key-form-error')
    expect(document.body.textContent).not.toContain('sk-')
    wrapper.unmount()
  })

  it('announces the pending save and clears busy state after the response', async () => {
    apiMocks.fetchModelGatewayKey.mockResolvedValue({
      configured: true,
      source: 'system',
      masked: '••••abcd',
    })
    const request = deferred<{ configured: boolean; source: 'system'; masked: string }>()
    apiMocks.updateModelGatewayKey.mockReturnValue(request.promise)
    const wrapper = mount(GatewayApiKeyDialog, { props: { open: true } })
    await flushPromises()

    const input = document.body.querySelector('.gateway-key-form input') as HTMLInputElement
    input.value = 'sk-test-secret'
    input.dispatchEvent(new Event('input', { bubbles: true }))
    await wrapper.vm.$nextTick()
    const form = document.body.querySelector('.gateway-key-form') as HTMLFormElement
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await wrapper.vm.$nextTick()

    const button = document.body.querySelector(
      '.gateway-key-form button[type="submit"]',
    ) as HTMLButtonElement
    expect(form.getAttribute('aria-busy')).toBe('true')
    expect(button.getAttribute('aria-busy')).toBe('true')
    expect(button.querySelector('[role="status"]')?.textContent).toContain('保存中')

    request.resolve({ configured: true, source: 'system', masked: '••••abcd' })
    await flushPromises()
    expect(form.getAttribute('aria-busy')).toBe('false')
    expect(button.getAttribute('aria-busy')).toBe('false')
    wrapper.unmount()
  })
})
