import type { KnowledgeBaseColumn, KnowledgeBaseForm } from './type'
/** 知识库管理页面逻辑：按当前空间读取列表并创建知识库。 */
import type { KnowledgeBaseRow } from '@/api/admin'
import { ref, watch } from 'vue'
import { createKnowledgeBase, fetchKnowledgeBases } from '@/api/admin'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

const EMPTY_FORM: KnowledgeBaseForm = {
  tenant_id: '',
  name: '',
  description: '',
  purpose: 'general',
}

/** 提供页面列表状态、创建流程和空间切换后的重新读取。 */
export function useKnowledgeBasesPage() {
  const auth = useAuthStore()
  const toast = useAppToast()
  const rows = ref<KnowledgeBaseRow[]>([])
  const loading = ref(false)
  const loadError = ref('')
  const dialogOpen = ref(false)
  const saving = ref(false)
  const form = ref<KnowledgeBaseForm>({ ...EMPTY_FORM })

  const columns: KnowledgeBaseColumn[] = [
    { key: 'name', title: '知识库名称' },
    { key: 'purpose', title: '用途', field: 'purpose' },
    { key: 'documents', title: '文档数' },
    { key: 'status', title: '状态' },
    { key: 'updated', title: '更新时间' },
  ]

  /** 只请求当前认证上下文中的空间，避免列表跨空间读取。 */
  async function loadData(): Promise<void> {
    loading.value = true
    loadError.value = ''
    try {
      rows.value = auth.activeSpaceId ? (await fetchKnowledgeBases(auth.activeSpaceId)).items : []
    } catch (cause) {
      loadError.value = cause instanceof Error ? cause.message : '数据加载失败'
      toast.error(loadError.value)
    } finally {
      loading.value = false
    }
  }

  /** 创建时冻结当前空间 ID；服务端仍负责最终授权校验。 */
  function openCreateDialog(): void {
    form.value = { ...EMPTY_FORM, tenant_id: auth.activeSpaceId }
    dialogOpen.value = true
  }

  /** 提交创建请求，成功后刷新列表；失败时保留表单以便修正或重试。 */
  async function saveKnowledgeBase(payload: KnowledgeBaseForm): Promise<void> {
    saving.value = true
    try {
      await createKnowledgeBase({ ...payload, tenant_id: Number(payload.tenant_id) })
      dialogOpen.value = false
      toast.success('知识库已创建')
      await loadData()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '知识库创建失败')
    } finally {
      saving.value = false
    }
  }

  watch(() => auth.activeSpaceId, loadData, { immediate: true })

  return {
    auth,
    rows,
    loading,
    loadError,
    dialogOpen,
    saving,
    form,
    columns,
    loadData,
    openCreateDialog,
    saveKnowledgeBase,
  }
}
