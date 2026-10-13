/** 客户空间页面逻辑：加载空间、创建医院空间并管理其 API Key。 */
import type { TenantRow } from '@/api/admin'
import type { CreatedApiKey } from '@/api/apiKeys'
import type { ApiKeyCreatePayload } from '@/views/models/components/ApiKeyCreateDialog/type'
import { ref } from 'vue'
import { createTenant, fetchTenants } from '@/api/admin'
import { createApiKey, fetchApiKeyPlaintext } from '@/api/apiKeys'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'
import { copyText } from '@/utils/clipboard'

/** 为页面提供空间数据及创建、配置和复制 Key 的异步操作。 */
export function useSpacesPage() {
  const auth = useAuthStore()
  const toast = useAppToast()
  const tenants = ref<TenantRow[]>([])
  const loading = ref(false)
  const loadError = ref('')
  const showCreateDialog = ref(false)
  const savingTenant = ref(false)
  const selectedTenantForKey = ref<TenantRow | null>(null)
  const tenantKeyDialogOpen = ref(false)
  const tenantKeySubmitting = ref(false)
  const revealedTenantKey = ref<CreatedApiKey | null>(null)
  const canCreateSpace = ref(false)
  const isPlatformAdmin = auth.user?.platform_role === 'platform_admin'

  /** 加载权威空间列表；错误同时保留页面重试入口。 */
  async function loadTenants(): Promise<void> {
    loading.value = true
    loadError.value = ''
    try {
      const result = await fetchTenants()
      tenants.value = result.items
      canCreateSpace.value = Boolean(result.can_create ?? isPlatformAdmin)
    } catch (cause) {
      loadError.value = cause instanceof Error ? cause.message : '空间列表加载失败'
      toast.error(loadError.value)
    } finally {
      loading.value = false
    }
  }

  /** 创建后刷新认证上下文并选中新空间，保持工作台当前空间与服务端一致。 */
  async function createSpace(form: { code: string; name: string }): Promise<boolean> {
    savingTenant.value = true
    try {
      const tenant = await createTenant({ ...form, code: form.code.trim().toLowerCase() })
      await auth.refreshContext()
      auth.setActiveSpace(tenant.id)
      toast.success('客户空间已创建')
      await loadTenants()
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '空间创建失败')
      return false
    } finally {
      savingTenant.value = false
    }
  }

  /** 只允许为启用且尚无 Key 的空间打开配置表单。 */
  function openKeyDialog(tenant: TenantRow): void {
    if (tenant.status !== 'active') return
    if (!isPlatformAdmin) {
      selectedTenantForKey.value = tenant
      tenantKeyDialogOpen.value = true
      return
    }
    if (tenant.api_key_id) return
    selectedTenantForKey.value = tenant
    tenantKeyDialogOpen.value = true
  }

  /** 创建医院级客户 Key，并保留明文给一次性展示弹窗。 */
  async function saveTenantKey(payload: ApiKeyCreatePayload): Promise<void> {
    tenantKeySubmitting.value = true
    try {
      revealedTenantKey.value = await createApiKey(payload)
      tenantKeyDialogOpen.value = false
      toast.success('客户 API Key 已配置', '请立即复制并通过安全渠道发放给客户。')
      await loadTenants()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '客户 API Key 配置失败')
    } finally {
      tenantKeySubmitting.value = false
    }
  }

  /** 交接组件确认成功后关闭弹窗并刷新列表的最新配置状态。 */
  async function finishTenantKeyConfiguration(): Promise<void> {
    tenantKeyDialogOpen.value = false
    await loadTenants()
  }

  /** 通过受保护接口取回完整 Key 并复制；列表状态始终只包含脱敏前缀。 */
  async function copyTenantKey(tenant: TenantRow): Promise<void> {
    if (!tenant.api_key_id) return
    try {
      const result = await fetchApiKeyPlaintext(tenant.api_key_id)
      await copyText(result.raw_key)
      toast.success('完整客户 API Key 已复制', '请通过安全渠道发放，页面不会保存明文。')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '客户 API Key 复制失败')
    }
  }

  return {
    tenants,
    canCreateSpace,
    isPlatformAdmin,
    loading,
    loadError,
    showCreateDialog,
    savingTenant,
    selectedTenantForKey,
    tenantKeyDialogOpen,
    tenantKeySubmitting,
    revealedTenantKey,
    loadTenants,
    createSpace,
    openKeyDialog,
    saveTenantKey,
    finishTenantKeyConfiguration,
    copyTenantKey,
    closeKeyReveal: () => {
      revealedTenantKey.value = null
    },
    toast,
  }
}
