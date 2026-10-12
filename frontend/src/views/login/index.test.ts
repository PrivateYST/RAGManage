// @vitest-environment happy-dom
/**
 * 登录表单无障碍回归：空凭据提交时，错误节点必须可播报并与两个输入字段关联，
 * 防止键盘或屏幕阅读器用户只能看到孤立的错误文案而无法定位修正位置。
 */
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { useLoginPage } from './index'
import LoginView from './index.vue'

const push = vi.fn()
const signIn = vi.fn()
const toastError = vi.fn()
let authState = reactive({ loading: false, error: '', signIn })

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ error: toastError }),
}))
vi.mock('@/store/auth', () => ({
  useAuthStore: () => authState,
}))

describe('login view', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setActivePinia(createPinia())
    authState = reactive({ loading: false, error: '', signIn })
  })

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

  it('trims the account name and routes to the guard-selected entry after login', async () => {
    signIn.mockResolvedValueOnce(true)
    const page = useLoginPage()
    page.form.value.loginName = '  admin  '
    page.form.value.password = 'secret'

    await expect(page.submit()).resolves.toBe('authenticated')

    expect(signIn).toHaveBeenCalledWith('admin', 'secret')
    expect(push).toHaveBeenCalledWith('/')
  })

  it('reports failed authentication and keeps the user on the form', async () => {
    authState.error = '凭据错误'
    signIn.mockResolvedValueOnce(false)
    const page = useLoginPage()
    page.form.value.loginName = 'admin'
    page.form.value.password = 'wrong'

    await expect(page.submit()).resolves.toBe('rejected')

    expect(toastError).toHaveBeenCalledWith('凭据错误')
    expect(push).not.toHaveBeenCalled()
  })
})
