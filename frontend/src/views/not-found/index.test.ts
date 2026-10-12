// @vitest-environment happy-dom
/** 404 页面迁移回归：未知路径反馈保持可访问，返回按钮继续交给路由守卫解析。 */
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import NotFoundPage from './index.vue'

const router = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('vue-router', () => ({ useRouter: () => router }))

describe('not found page migration', () => {
  it('renders the not-found explanation and returns to the guarded workspace entry', async () => {
    const wrapper = mount(NotFoundPage)

    expect(wrapper.get('h1').text()).toBe('找不到这个页面')
    expect(wrapper.text()).toContain('链接可能已失效，或者你当前没有访问这个菜单的权限。')
    expect(router.push).not.toHaveBeenCalled()

    await wrapper.get('button').trigger('click')

    expect(router.push).toHaveBeenCalledOnce()
    expect(router.push).toHaveBeenCalledWith('/')
  })
})
