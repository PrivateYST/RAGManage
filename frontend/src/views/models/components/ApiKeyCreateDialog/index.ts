/** API Key 创建表单状态与校验，服务端仍执行最终权限和参数校验。 */
import type { ApiKeyCreateDialogProps, ApiKeyCreatePayload } from './type'
import { reactive, shallowRef, watch } from 'vue'

/** 管理发放表单的重置、前端校验和规范化提交数据。 */
export function useApiKeyCreateDialog(
  props: ApiKeyCreateDialogProps,
  emit: (event: 'submit', payload: ApiKeyCreatePayload) => void,
) {
  const form = reactive({ tenantId: '', name: '', tokenLimit: '100000', expiresAt: '' })
  const error = shallowRef('')

  watch(
    () => props.open,
    (open) => {
      if (!open)
        return
      form.tenantId = props.tenants[0]?.id ?? ''
      form.name = ''
      form.tokenLimit = '100000'
      form.expiresAt = ''
      error.value = ''
    },
    { immediate: true },
  )

  /** 校验必填项和正整数额度，再向父组件提交标准接口负载。 */
  function submit(): void {
    const tokenLimit = Number(form.tokenLimit)
    if (!form.tenantId || !form.name.trim() || !Number.isInteger(tokenLimit) || tokenLimit <= 0) {
      error.value = '请填写客户、名称和正整数 Token 额度'
      return
    }
    emit('submit', {
      tenant_id: Number(form.tenantId),
      name: form.name.trim(),
      token_limit: tokenLimit,
      expires_at: form.expiresAt
        ? new Date(`${form.expiresAt}T23:59:59`).toISOString()
        : null,
    })
  }

  return { form, error, submit }
}
