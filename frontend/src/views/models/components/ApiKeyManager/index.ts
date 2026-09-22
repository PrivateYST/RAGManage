/** API Key 管理容器的异步编排：加载租户、发放 Key、状态切换、删除和查询流水。 */
import type { ApiKeyCreatePayload } from '../ApiKeyCreateDialog/type'
import type { TenantRow } from '@/api/admin'
import type {
  ApiKeyUsageRow,
  ApiKeyUsageSummary,
  CompanyApiKey,
  CreatedApiKey,
} from '@/api/apiKeys'
import { onMounted, shallowRef } from 'vue'
import { fetchTenants } from '@/api/admin'
import {
  createApiKey,
  deleteApiKey,
  fetchApiKeyPlaintext,
  fetchApiKeys,
  fetchApiKeyUsage,
  updateApiKeyStatus,
} from '@/api/apiKeys'
import { useAppToast } from '@/composables/useToast'

/** 管理 API Key 页面状态，并串联创建、状态切换、删除、用量查询及用户反馈。 */
export function useApiKeyManager() {
  const toast = useAppToast()
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
  const createOpen = shallowRef(false)
  const revealedKey = shallowRef<CreatedApiKey | null>(null)
  const pendingDelete = shallowRef<CompanyApiKey | null>(null)
  const pendingStatus = shallowRef<CompanyApiKey | null>(null)

  /** 打开创建弹窗，表单状态由子组件在打开时重置。 */
  function openCreate(): void {
    createOpen.value = true
  }

  /** 并行加载 Key 和可发放的启用客户空间。 */
  async function load(): Promise<void> {
    loading.value = true
    try {
      const [keyResult, tenantResult] = await Promise.all([fetchApiKeys(), fetchTenants()])
      items.value = keyResult.items
      tenants.value = tenantResult.items.filter((item) => item.status === 'active')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'API Key 加载失败')
    } finally {
      loading.value = false
    }
  }

  /** 发放 Key 并保留仅本次响应可见的明文。 */
  async function submit(payload: ApiKeyCreatePayload): Promise<void> {
    submitting.value = true
    try {
      revealedKey.value = await createApiKey(payload)
      createOpen.value = false
      toast.success('API Key 已创建', '请立即复制并安全下发；关闭后不会再次显示明文。')
      items.value = (await fetchApiKeys()).items
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'API Key 创建失败')
    } finally {
      submitting.value = false
    }
  }

  /** 进入删除确认态，避免单击即破坏客户凭据。 */
  function requestDelete(item: CompanyApiKey): void {
    pendingDelete.value = item
  }

  /** 退出删除确认态，不修改服务端状态。 */
  function cancelDelete(): void {
    pendingDelete.value = null
  }

  /** 确认软删除当前 Key，并刷新服务端列表。 */
  async function confirmDelete(): Promise<void> {
    const item = pendingDelete.value
    if (!item) return
    busyId.value = item.id
    try {
      await deleteApiKey(item.id)
      toast.success('API Key 已删除并立即失效')
      items.value = (await fetchApiKeys()).items
      pendingDelete.value = null
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'API Key 删除失败')
    } finally {
      busyId.value = ''
    }
  }

  /** 停用凭据会立即阻断调用，先进入确认态；重新启用可以直接执行。 */
  async function toggleStatus(item: CompanyApiKey): Promise<void> {
    if (item.status !== 'active' && item.status !== 'disabled') return
    if (item.status === 'active') {
      pendingStatus.value = item
      return
    }
    await updateStatus(item)
  }

  /** 执行已经确认的 API Key 状态变更，并以服务端列表作为唯一事实来源。 */
  async function updateStatus(item: CompanyApiKey): Promise<boolean> {
    busyId.value = item.id
    const nextStatus = item.status === 'active' ? 'disabled' : 'active'
    try {
      await updateApiKeyStatus(item.id, nextStatus)
      toast.success(nextStatus === 'active' ? 'API Key 已启用' : 'API Key 已停用')
      items.value = (await fetchApiKeys()).items
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'API Key 状态更新失败')
      return false
    } finally {
      busyId.value = ''
    }
  }

  /** 关闭 API Key 停用确认态，不修改服务端状态。 */
  function cancelStatus(): void {
    if (!busyId.value) pendingStatus.value = null
  }

  /** 确认停用当前 API Key。 */
  async function confirmStatus(): Promise<void> {
    const item = pendingStatus.value
    if (!item) return
    if (await updateStatus(item)) pendingStatus.value = null
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
      if (requestSequence !== usageRequestSequence || selected.value?.id !== item.id) return
      usage.value = result.items
      usageSummary.value = result.summary
      usageRecentLimit.value = result.recent_limit
    } catch (cause) {
      if (requestSequence !== usageRequestSequence) return
      toast.error(cause instanceof Error ? cause.message : '用量加载失败')
    } finally {
      if (requestSequence === usageRequestSequence) usageLoading.value = false
    }
  }

  /** 接收明文弹窗的复制成功事件并显示反馈。 */
  async function copyRevealedKey(): Promise<void> {
    toast.success('API Key 已复制')
  }

  /** 通过管理员接口读取并复制完整 Key；旧 Key 无密文时提示重新发放。 */
  async function copyKeyIdentifier(item: CompanyApiKey): Promise<void> {
    try {
      const result = await fetchApiKeyPlaintext(item.id)
      await navigator.clipboard.writeText(result.raw_key)
      toast.success('完整 API Key 已复制', '请通过安全渠道下发。')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '完整 API Key 复制失败')
    }
  }

  /** 关闭明文弹窗并从页面状态中移除当前响应中的 Key。 */
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
    createOpen,
    revealedKey,
    pendingDelete,
    pendingStatus,
    load,
    openCreate,
    submit,
    requestDelete,
    cancelDelete,
    confirmDelete,
    toggleStatus,
    cancelStatus,
    confirmStatus,
    showUsage,
    copyRevealedKey,
    copyKeyIdentifier,
    closeRevealedKey,
  }
}
