// @vitest-environment happy-dom

/**
 * AlertDialog 封装回归测试：确认和取消必须通过受控事件回传，
 * 异步 busy 状态下不能意外关闭或重复触发破坏性操作。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppConfirmDialog from './index.vue'

describe('app confirm dialog', () => {
  it('emits cancel and closes through the controlled model', async () => {
    const wrapper = mount(AppConfirmDialog, {
      props: { open: true, title: '删除项目', description: '删除后不可恢复' },
    })
    await wrapper.vm.$nextTick()

    const dialog = document.body.querySelector('[role="alertdialog"]')
    expect(dialog).not.toBeNull()
    expect(dialog?.textContent).toContain('删除项目')

    const cancel = Array.from(dialog?.querySelectorAll('button') ?? []).find((button) =>
      button.textContent?.includes('取消'),
    )
    cancel?.click()
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:open')).toEqual([[false]])
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    wrapper.unmount()
  })

  it('keeps the dialog open while a destructive request is busy', async () => {
    const wrapper = mount(AppConfirmDialog, {
      props: {
        open: true,
        title: '删除项目',
        description: '删除后不可恢复',
        busy: true,
      },
    })
    await wrapper.vm.$nextTick()

    const dialog = document.body.querySelector('[role="alertdialog"]')
    const buttons = Array.from(dialog?.querySelectorAll('button') ?? [])
    buttons[0]?.click()
    buttons.at(-1)?.click()
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('update:open')).toBeUndefined()
    expect(wrapper.emitted('cancel')).toBeUndefined()
    expect(wrapper.emitted('confirm')).toBeUndefined()
    wrapper.unmount()
  })
})
