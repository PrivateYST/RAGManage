/** 登录页逻辑：收集凭据、调用认证 Store 并由动态路由守卫决定默认入口。 */
import type { LoginFormState, LoginSubmitResult } from './type'
import { computed, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

/** 创建登录页状态和提交动作，供页面模板以 refs 绑定输入。 */
export function useLoginPage() {
  const router = useRouter()
  const auth = useAuthStore()
  const toast = useAppToast()
  const form = ref<LoginFormState>({ loginName: '', password: '' })
  const submitted = shallowRef(false)
  const canSubmit = computed(
    () => form.value.loginName.trim().length > 0 && form.value.password.length > 0 && !auth.loading,
  )

  /** 校验后提交认证；登录失败通过全局 Toast 反馈，成功交由守卫选择动态入口。 */
  async function submit(): Promise<LoginSubmitResult> {
    submitted.value = true
    if (!canSubmit.value) return 'invalid'
    if (await auth.signIn(form.value.loginName.trim(), form.value.password)) {
      await router.push('/')
      return 'authenticated'
    }
    toast.error(auth.error || '登录失败，请稍后重试')
    return 'rejected'
  }

  return { auth, form, submitted, canSubmit, submit }
}
