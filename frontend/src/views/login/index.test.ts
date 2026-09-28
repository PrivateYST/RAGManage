// @vitest-environment happy-dom
/**
 * 登录表单无障碍回归：空凭据提交时，错误节点必须可播报并与两个输入字段关联，
 * 防止键盘或屏幕阅读器用户只能看到孤立的错误文案而无法定位修正位置。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import LoginView from './index.vue'

const push = vi.fn()
const signIn = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ error: vi.fn() }),
}))
vi.mock('@/store/auth', () => ({
  useAuthStore: () => ({
    loading: false,
    error: null,
    signIn,
  }),
}))

describe('login view', () => {
  it('associates empty-credential feedback with both fields', async () => {
    const wrapper = mount(LoginView)
    await wrapper.get('form').trigger('submit')

    const error = wrapper.get('#login-error')
    expect(error.attributes('role')).toBe('alert')
    expect(error.attributes('aria-live')).toBe('polite')
    expect(wrapper.get('#login-name').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#login-password').attributes('aria-invalid')).toBe('true')
    expect(wrapper.get('#login-name').attributes('aria-describedby')).toBe('login-error')
    expect(wrapper.get('#login-password').attributes('aria-describedby')).toBe('login-error')
  })
})
