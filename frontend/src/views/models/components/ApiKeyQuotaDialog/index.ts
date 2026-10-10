/** API Key 额度调整弹窗的输入校验、额度预览和提交负载生成。 */
import type { ApiKeyQuotaDialogProps } from './type'
import type { ApiKeyQuotaAdjustment, ApiKeyQuotaDirection } from '@/api/apiKeys'
import { computed, reactive, shallowRef, watch } from 'vue'

/** 管理额度调整表单，并在提交前预览和校验新的总额度。 */
export function useApiKeyQuotaDialog(props: ApiKeyQuotaDialogProps) {
  const form = reactive<{ operation: ApiKeyQuotaDirection; amount: string }>({
    operation: 'add',
    amount: '1',
  })
  const error = shallowRef('')
  const adjustmentAmount = computed(() => Number(form.amount))
  const nextTokenLimit = computed(() => {
    const current = props.apiKey?.token_limit ?? 0
    const amount = Number.isFinite(adjustmentAmount.value) ? adjustmentAmount.value : 0
    return form.operation === 'add' ? current + amount : current - amount
  })
  const nextTokenRemaining = computed(() => {
    const usedAndReserved = (props.apiKey?.token_used ?? 0) + (props.apiKey?.token_reserved ?? 0)
    return Math.max(0, nextTokenLimit.value - usedAndReserved)
  })
  const maxAmount = computed(() => {
    if (!props.apiKey) return 0
    return form.operation === 'add'
      ? 10_000_000_000 - props.apiKey.token_limit
      : Math.min(props.apiKey.token_remaining, props.apiKey.token_limit - 1)
  })

  watch(
    () => [props.open, props.apiKey?.id] as const,
    ([open]) => {
      if (!open) return
      form.operation = 'add'
      form.amount = '1'
      error.value = ''
    },
  )

  /** 验证增减数量和额度上限，再返回服务端保存的绝对总额度。 */
  function submit(): ApiKeyQuotaAdjustment | null {
    const amount = adjustmentAmount.value
    if (!props.apiKey || !Number.isSafeInteger(amount) || amount <= 0) {
      error.value = '请输入大于 0 的整数 Token 数量'
      return null
    }
    if (amount > maxAmount.value) {
      error.value =
        form.operation === 'subtract'
          ? '减少数量不能超过当前可用余额'
          : '调整后的总额度不能超过 10,000,000,000 Token'
      return null
    }
    error.value = ''
    return { direction: form.operation, amount }
  }

  return { form, error, adjustmentAmount, nextTokenLimit, nextTokenRemaining, maxAmount, submit }
}
