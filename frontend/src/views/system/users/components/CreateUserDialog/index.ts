/** 新建用户表单逻辑：根据平台角色等级构造后端平台或医院成员角色。 */
import type { CreateUserForm } from '../../type'
import type { UserCreatePayload } from '@/api/admin'
import { ref } from 'vue'
import { createUser } from '@/api/admin'
import { useAppToast } from '@/composables/useToast'

/**
 * 将界面角色等级映射为后端既有角色契约，确保“系统管理员”只获得平台角色，
 * 医院管理员和普通用户则绑定医院及对应的空间成员角色。
 */
export function toUserCreatePayload(form: CreateUserForm): UserCreatePayload {
  return {
    login: form.login,
    display_name: form.display_name,
    password: form.password,
    ...(form.role_level === 'company_admin' ? { platform_role_code: 'platform_admin' } : {}),
    ...(form.role_level !== 'company_admin' && form.tenant_id
      ? {
          tenant_id: Number(form.tenant_id),
          tenant_role_code:
            form.role_level === 'hospital_admin' ? 'space_admin' : 'customer_reader',
        }
      : {}),
  }
}

/** 表单状态和提交操作由弹窗独立拥有，成功后通知页面刷新列表。 */
export function useCreateUserDialog() {
  const toast = useAppToast()
  const saving = ref(false)
  const form = ref<CreateUserForm>(emptyForm())

  /** 返回干净的初始表单，避免重复打开时复用上次密码或医院。 */
  function emptyForm(): CreateUserForm {
    return {
      login: '',
      display_name: '',
      password: '',
      role_level: 'ordinary',
      tenant_id: '',
    }
  }

  /** 重置凭据和角色状态后打开时，由父组件控制 open；此方法供弹窗初始化调用。 */
  function resetForm(): void {
    form.value = emptyForm()
  }

  /** 按业务等级映射平台角色或空间成员角色，并通过 Toast 报告请求结果。 */
  async function submit(): Promise<boolean> {
    saving.value = true
    try {
      await createUser(toUserCreatePayload(form.value))
      toast.success('用户已创建')
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '用户创建失败')
      return false
    } finally {
      saving.value = false
    }
  }

  return { form, saving, resetForm, submit }
}
