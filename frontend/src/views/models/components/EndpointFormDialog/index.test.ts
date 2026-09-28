// @vitest-environment happy-dom
/**
 * 模型端点表单回归：空模型白名单必须阻止提交，并将业务校验错误关联到对应 textarea，
 * 防止用户只看到错误文本却无法判断需要修正哪个字段。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EndpointFormDialog from './index.vue'

describe('endpoint form dialog', () => {
  it('associates whitelist validation feedback with the textarea', async () => {
    const wrapper = mount(EndpointFormDialog, {
      props: { open: true, endpoint: null },
    })
    await wrapper.vm.$nextTick()

    const form = document.body.querySelector('form') as HTMLFormElement
    expect(form).toBeTruthy()
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await wrapper.vm.$nextTick()

    const error = document.body.querySelector('#endpoint-form-error') as HTMLElement
    const whitelist = document.body.querySelector('textarea') as HTMLTextAreaElement
    expect(error.getAttribute('role')).toBe('alert')
    expect(error.getAttribute('aria-live')).toBe('polite')
    expect(whitelist.getAttribute('aria-invalid')).toBe('true')
    expect(whitelist.getAttribute('aria-describedby')).toBe('endpoint-form-error')
    expect(wrapper.emitted('submit')).toBeUndefined()
    wrapper.unmount()
  })
})
