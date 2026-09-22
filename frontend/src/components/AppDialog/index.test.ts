// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppDialog from './index.vue'

describe('app dialog', () => {
  it('does not close when the content area is clicked', async () => {
    const wrapper = mount(AppDialog, {
      props: { open: true, title: '上传文档' },
      slots: { default: '<button data-test="inside">内部按钮</button>' },
    })
    await wrapper.vm.$nextTick()

    const inside = document.body.querySelector('[data-test="inside"]') as HTMLElement
    inside.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0 }))
    inside.click()
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:open')).toBeUndefined()
    expect(wrapper.emitted('close')).toBeUndefined()
    wrapper.unmount()
  })

  it('renders an interactive overlay around the dialog', async () => {
    const wrapper = mount(AppDialog, {
      props: { open: true, title: '上传文档' },
      slots: { default: '<div>内容</div>' },
    })
    await wrapper.vm.$nextTick()

    const overlay = document.body.querySelector('[data-state="open"].fixed.inset-0') as HTMLElement
    expect(overlay).toBeTruthy()
    wrapper.unmount()
  })

})
