// @vitest-environment happy-dom
/**
 * API Key 创建表单回归：非法额度或缺少必填项时，校验错误必须关联到可修复字段，
 * 防止凭据发放表单只提示失败而无法定位输入问题。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ApiKeyCreateDialog from './index.vue'

describe('api key create dialog', () => {
  it('associates validation feedback with required credential fields', async () => {
    const wrapper = mount(ApiKeyCreateDialog, {
      props: { open: true, submitting: false, tenants: [] },
    })
    await wrapper.vm.$nextTick()

    const form = document.body.querySelector('form') as HTMLFormElement
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await wrapper.vm.$nextTick()

    const error = document.body.querySelector('#api-key-form-error') as HTMLElement
    expect(error.getAttribute('role')).toBe('alert')
    expect(error.getAttribute('aria-live')).toBe('polite')
    for (const field of document.body.querySelectorAll('select, input[required]')) {
      expect(field.getAttribute('aria-invalid')).toBe('true')
      expect(field.getAttribute('aria-describedby')).toBe('api-key-form-error')
    }
    wrapper.unmount()
  })

  it('announces credential generation while the parent request is pending', async () => {
    const wrapper = mount(ApiKeyCreateDialog, {
      props: {
        open: true,
        submitting: true,
        tenants: [
          {
            id: '1',
            code: 'test-space',
            name: '测试空间',
            status: 'active',
            member_count: 0,
            knowledge_base_count: 0,
            created_at: '2026-09-28T00:00:00Z',
            api_key_id: null,
            api_key_status: null,
            api_key_prefix: null,
            api_key_token_limit: null,
            api_key_token_used: null,
            api_key_token_remaining: null,
            api_key_expires_at: null,
          },
        ],
      },
    })
    await wrapper.vm.$nextTick()

    const form = document.body.querySelector('form') as HTMLFormElement
    const button = document.body.querySelector('button[type="submit"]') as HTMLButtonElement
    expect(form.getAttribute('aria-busy')).toBe('true')
    expect(button.getAttribute('aria-busy')).toBe('true')
    expect(button.querySelector('[role="status"]')?.textContent).toContain('生成中')
    wrapper.unmount()
  })
})
