/** 医院 API Key 交接确认逻辑：按当前空间读取脱敏状态并校验管理员粘贴的凭据。 */
import type { Ref } from 'vue'
import type { TenantApiKeyConfiguration } from '@/api/tenantApiKeys'
import { computed, onBeforeUnmount, shallowRef, watch } from 'vue'
import {
  confirmTenantApiKeyConfiguration,
  fetchTenantApiKeyConfiguration,
} from '@/api/tenantApiKeys'
import { useAppToast } from '@/composables/useToast'

/** 管理单一医院的 Key 交接；请求只登记确认元数据，敏感字符串不持久化到客户端状态之外。 */
export function useTenantApiKeyConfig(tenantId: Ref<string>) {
  const toast = useAppToast()
  let requestSequence = 0
  const configuration = shallowRef<TenantApiKeyConfiguration | null>(null)
  const loading = shallowRef(false)
  const submitting = shallowRef(false)
  const apiKey = shallowRef('')
  const showApiKey = shallowRef(false)
  const error = shallowRef('')

  const canSubmit = computed(
    () => configuration.value?.status === 'active' && Boolean(configuration.value.key_prefix),
  )

  /** 切换空间时丢弃旧状态和输入，并忽略旧空间迟到的响应。 */
  async function load(): Promise<void> {
    const tenantIdAtStart = tenantId.value
    const sequence = ++requestSequence
    configuration.value = null
    apiKey.value = ''
    error.value = ''
    if (!tenantIdAtStart) {
      loading.value = false
      return
    }

    loading.value = true
    try {
      const result = await fetchTenantApiKeyConfiguration(tenantIdAtStart)
      if (sequence === requestSequence && tenantId.value === tenantIdAtStart)
        configuration.value = result
    } catch (cause) {
      if (sequence !== requestSequence || tenantId.value !== tenantIdAtStart) return
      error.value = cause instanceof Error ? cause.message : '医院 API Key 状态加载失败'
      toast.error(error.value)
    } finally {
      if (sequence === requestSequence) loading.value = false
    }
  }

  /** 将粘贴的 Key 发给当前医院范围的校验接口，成功后立即清除本地明文。 */
  async function submit(): Promise<boolean> {
    const tenantIdAtStart = tenantId.value
    const normalizedKey = apiKey.value.trim()
    if (!tenantIdAtStart || !canSubmit.value || !normalizedKey) return false

    submitting.value = true
    error.value = ''
    try {
      const result = await confirmTenantApiKeyConfiguration(tenantIdAtStart, normalizedKey)
      if (tenantId.value !== tenantIdAtStart) return false
      configuration.value = result
      apiKey.value = ''
      toast.success('医院 API Key 已确认配置', '系统只保留交接状态，不保存或回显 Key 明文。')
      return true
    } catch (cause) {
      if (tenantId.value !== tenantIdAtStart) return false
      error.value = cause instanceof Error ? cause.message : '医院 API Key 配置确认失败'
      toast.error(error.value)
      return false
    } finally {
      submitting.value = false
    }
  }

  watch(tenantId, load, { immediate: true })
  onBeforeUnmount(() => {
    requestSequence += 1
    apiKey.value = ''
  })

  return { configuration, loading, submitting, apiKey, showApiKey, error, canSubmit, load, submit }
}
