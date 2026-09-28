// @vitest-environment happy-dom
/**
 * 添加成员弹窗无障碍回归：提交回调未完成时，表单必须进入忙碌状态并播报处理中，
 * 防止用户重复点击造成重复授权；父级完成回调后状态才恢复可操作。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AddMemberDialog from './index.vue'

describe('add member dialog', () => {
  it('announces pending member creation and clears it after completion', async () => {
    const wrapper = mount(AddMemberDialog, { props: { open: true } })
    await wrapper.vm.$nextTick()

    const login = document.body.querySelector(
      'input[placeholder="例如 zhangsan"]',
    ) as HTMLInputElement
    login.value = 'zhangsan'
    login.dispatchEvent(new Event('input', { bubbles: true }))
    await wrapper.vm.$nextTick()

    const submit = document.body.querySelector('button[type="submit"]') as HTMLButtonElement
    submit.click()
    await wrapper.vm.$nextTick()

    const form = document.body.querySelector('form') as HTMLFormElement
    expect(form.getAttribute('aria-busy')).toBe('true')
    expect(submit.getAttribute('aria-busy')).toBe('true')
    expect(submit.querySelector('[role="status"]')?.textContent).toContain('添加中')

    const submission = wrapper.emitted('submit')?.[0]
    const done = submission?.[1] as ((success: boolean) => void) | undefined
    expect(done).toBeTypeOf('function')
    done?.(false)
    await wrapper.vm.$nextTick()
    expect(form.getAttribute('aria-busy')).toBe('false')
    expect(submit.getAttribute('aria-busy')).toBe('false')
    wrapper.unmount()
  })
})
