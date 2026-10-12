// @vitest-environment happy-dom

/** 输入区回归：键盘与按钮提交同一发送事件，生成中显示停止操作。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ChatComposer from './index.vue'

describe('chat composer', () => {
  it('sends on submit and Ctrl+Enter', async () => {
    const wrapper = mount(ChatComposer, {
      props: { modelValue: '问题', sending: false, canSend: true, disabledReason: '' },
    })

    await wrapper.get('form').trigger('submit')
    await wrapper.get('textarea').trigger('keydown.ctrl.enter')

    expect(wrapper.emitted('send')).toHaveLength(2)
  })

  it('offers stop instead of send while an answer is generating', async () => {
    const wrapper = mount(ChatComposer, {
      props: { modelValue: '问题', sending: true, canSend: false, disabledReason: '' },
    })

    await wrapper.get('button').trigger('click')

    expect(wrapper.text()).toContain('停止')
    expect(wrapper.emitted('stop')).toHaveLength(1)
    expect(wrapper.find('button[type="submit"]').exists()).toBe(false)
  })
})
