/** 用户编辑提交逻辑：只开放后端 PATCH 接口允许修改的资料字段。 */
import type { TenantRow, UserDetail, UserRow } from '@/api/admin'
import { ref, watch } from 'vue'
import { fetchUserDetail, updateUser } from '@/api/admin'
import { useAppToast } from '@/composables/useToast'

/** 将账号资料载入编辑表单，并在请求期间阻止重复提交。 */
export function useEditUserDialog(getUser: () => UserRow | null, tenants: TenantRow[]) {
  const toast = useAppToast()
  const displayName = ref('')
  const password = ref('')
  const roleLevel = ref<'company_admin' | 'hospital_admin' | 'ordinary'>('ordinary')
  const tenantId = ref('')
  const originalTenantId = ref('')
  const detail = ref<UserDetail | null>(null)
  const saving = ref(false)

  watch(getUser, async (user) => {
    displayName.value = user?.display_name ?? ''
    password.value = ''
    detail.value = null
    if (!user) return
    try {
      detail.value = await fetchUserDetail(user.id)
      const membership = detail.value.memberships.find(item => item.status === 'active')
      originalTenantId.value = membership?.tenant_id ?? ''
      tenantId.value = originalTenantId.value
      roleLevel.value = user.platform_role
        ? 'company_admin'
        : membership?.role_code === 'space_admin' ? 'hospital_admin' : 'ordinary'
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '用户角色信息加载失败')
    }
  }, { immediate: true })

  /** 密码留空时不更新凭据，避免编辑普通资料时意外重置密码。 */
  async function save(): Promise<boolean> {
    const user = getUser()
    if (!user) return false
    saving.value = true
    try {
      await updateUser(user.id, {
        display_name: displayName.value.trim(),
        ...(password.value ? { password: password.value } : {}),
        platform_role_code: roleLevel.value === 'company_admin' ? 'platform_admin' : null,
        ...(roleLevel.value === 'company_admin'
          ? { tenant_id: null, tenant_role_code: null }
          : tenantId.value
            ? {
                tenant_id: Number(tenantId.value),
                tenant_role_code: roleLevel.value === 'hospital_admin' ? 'space_admin' : 'customer_reader',
              }
            : { tenant_id: null, tenant_role_code: null }),
      })
      toast.success('用户资料已更新')
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '用户资料更新失败')
      return false
    } finally {
      saving.value = false
    }
  }

  return { displayName, password, roleLevel, tenantId, originalTenantId, detail, tenants, saving, save }
}
