/** API Key 管理容器的异步编排：加载租户、发放 Key、撤销和查询流水。 */
import type { ApiKeyCreatePayload } from '../ApiKeyCreateDialog/type'
import type { ApiKeyManagerNotice } from './type'
import type { TenantRow } from '@/api/admin'
import type {
  ApiKeyUsageRow,
  ApiKeyUsageSummary,
  CompanyApiKey,
  CreatedApiKey,
} from '@/api/apiKeys'
import { onMounted, shallowRef } from 'vue'
import { fetchTenants } from '@/api/admin'
import { createApiKey, fetchApiKeys, fetchApiKeyUsage, revokeApiKey } from '@/api/apiKeys'

/** 管理 API Key 页面状态，并串联创建、撤销、用量查询及用户反馈。 */
export function useApiKeyManager() {
  // 序号只存在于页面生命周期内，用于阻止快速切换 Key 时旧响应覆盖新选择。
  let usageRequestSequence = 0
  const items = shallowRef<CompanyApiKey[]>([])
  const tenants = shallowRef<TenantRow[]>([])
  const selected = shallowRef<CompanyApiKey | null>(null)
  const usage = shallowRef<ApiKeyUsageRow[]>([])
  const usageSummary = shallowRef<ApiKeyUsageSummary | null>(null)
  const usageRecentLimit = shallowRef(200)
  const loading = shallowRef(false)
  const usageLoading = shallowRef(false)
  const submitting = shallowRef(false)
  const busyId = shallowRef('')
  const error = shallowRef('')
  const success = shallowRef<ApiKeyManagerNotice>('')
  const createOpen = shallowRef(false)
  const revealedKey = shallowRef<CreatedApiKey | null>(null)
  const pendingRevoke = shallowRef<CompanyApiKey | null>(null)

  /** 清除上一次操作反馈，避免新操作与旧状态并列。 */
  function clearNotice(): void {
    error.value = ''
    success.value = ''
  }

  /** 打开创建弹窗，表单状态由子组件在打开时重置。 */
  function openCreate(): void {
    createOpen.value = true
  }

  /** 并行加载 Key 和可发放的启用客户空间。 */
  async function load(): Promise<void> {
    loading.value = true
    clearNotice()
    try {
      const [keyResult, tenantResult] = await Promise.all([fetchApiKeys(), fetchTenants()])
      items.value = keyResult.items
      tenants.value = tenantResult.items.filter(item => item.status === 'active')
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'API Key 加载失败'
    }
    finally {
      loading.value = false
    }
  }

  /** 发放 Key 并保留仅本次响应可见的明文。 */
  async function submit(payload: ApiKeyCreatePayload): Promise<void> {
    submitting.value = true
    clearNotice()
    try {
      revealedKey.value = await createApiKey(payload)
      createOpen.value = false
      success.value = 'API Key 已创建，请立即复制并安全下发；关闭后不会再次显示明文。'
      items.value = (await fetchApiKeys()).items
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'API Key 创建失败'
    }
    finally {
      submitting.value = false
    }
  }

  /** 进入撤销确认态，避免单击即破坏客户凭据。 */
  function requestRevoke(item: CompanyApiKey): void {
    pendingRevoke.value = item
  }

  /** 退出撤销确认态，不修改服务端状态。 */
  function cancelRevoke(): void {
    pendingRevoke.value = null
  }

  /** 确认撤销当前 Key，并刷新服务端汇总状态。 */
  async function confirmRevoke(): Promise<void> {
    const item = pendingRevoke.value
    if (!item)
      return
    busyId.value = item.id
    clearNotice()
    try {
      await revokeApiKey(item.id)
      success.value = 'API Key 已撤销'
      items.value = (await fetchApiKeys()).items
      pendingRevoke.value = null
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'API Key 撤销失败'
    }
    finally {
      busyId.value = ''
    }
  }

  /** 查询选中 Key 的全量摘要与最近流水，忽略较早请求的迟到响应。 */
  async function showUsage(item: CompanyApiKey): Promise<void> {
    const requestSequence = ++usageRequestSequence
    selected.value = item
    usage.value = []
    usageSummary.value = null
    usageRecentLimit.value = 200
    usageLoading.value = true
    try {
      const result = await fetchApiKeyUsage(item.id)
      if (requestSequence !== usageRequestSequence || selected.value?.id !== item.id)
        return
      usage.value = result.items
      usageSummary.value = result.summary
      usageRecentLimit.value = result.recent_limit
    }
    catch (cause) {
      if (requestSequence !== usageRequestSequence)
        return
      error.value = cause instanceof Error ? cause.message : '用量加载失败'
    }
    finally {
      if (requestSequence === usageRequestSequence)
        usageLoading.value = false
    }
  }

  /** 接收明文弹窗的复制成功事件并显示反馈。 */
  async function copyRevealedKey(): Promise<void> {
    success.value = 'API Key 已复制'
  }

  /** 关闭明文弹窗并从响应式状态中移除不可再次读取的 Key。 */
  function closeRevealedKey(): void {
    revealedKey.value = null
  }

  onMounted(load)

  return {
    items,
    tenants,
    selected,
    usage,
    usageSummary,
    usageRecentLimit,
    loading,
    usageLoading,
    submitting,
    busyId,
    error,
    success,
    createOpen,
    revealedKey,
    pendingRevoke,
    load,
    openCreate,
    submit,
    requestRevoke,
    cancelRevoke,
    confirmRevoke,
    showUsage,
    copyRevealedKey,
    closeRevealedKey,
  }
}
