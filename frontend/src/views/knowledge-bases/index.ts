import type { KnowledgeBaseColumn, KnowledgeBaseForm } from './type'
/** 知识库管理页面逻辑：按当前空间读取列表并创建知识库。 */
import type { KnowledgeBaseRow } from '@/api/admin'
import type { SpaceMember } from '@/api/members'
import { ref, watch } from 'vue'
import { createKnowledgeBase, fetchKnowledgeBases, updateKnowledgeBaseGovernance } from '@/api/admin'
import { fetchSpaceMembers } from '@/api/members'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

const EMPTY_FORM: KnowledgeBaseForm = {
  tenant_id: '',
  name: '',
  description: '',
  purpose: 'general',
  business_scenario: '',
  target_users: '',
  owner_user_id: '',
  trust_level: 'medium',
  valid_from: '',
  valid_until: '',
  source_system: '',
  business_tags: '',
}
const BUSINESS_TAG_SEPARATOR = /[,，]/

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
  const wikiOpen = ref(false)
  const wikiRow = ref<KnowledgeBaseRow | null>(null)

  /** 冻结当前知识库上下文，避免词条误归属到其他空间。 */
  function openWiki(row: KnowledgeBaseRow): void {
    wikiRow.value = row
    wikiOpen.value = true
  }
  const editDialogOpen = ref(false)
  const editSaving = ref(false)
  const editingRow = ref<KnowledgeBaseRow | null>(null)
  const members = ref<SpaceMember[]>([])
  const editForm = ref<KnowledgeBaseForm>({ ...EMPTY_FORM })

  const columns: KnowledgeBaseColumn[] = [
    { key: 'name', title: '知识库名称' },
    { key: 'purpose', title: '用途', field: 'purpose' },
    { key: 'business_scenario', title: '业务场景', field: 'business_scenario' },
    { key: 'trust_level', title: '可信等级', field: 'trust_level' },
    { key: 'source_system', title: '来源系统', field: 'source_system' },
    { key: 'documents', title: '文档数' },
    { key: 'status', title: '状态' },
    { key: 'updated', title: '更新时间' },
    { key: 'actions', title: '操作' },
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

  /** 打开治理编辑并加载当前空间成员，负责人只能从有效成员中选择。 */
  async function openGovernanceDialog(row: KnowledgeBaseRow): Promise<void> {
    editingRow.value = row
    editForm.value = { ...EMPTY_FORM, tenant_id: row.tenant_id, business_scenario: row.business_scenario || '', target_users: row.target_users || '', owner_user_id: row.owner_user_id || '', trust_level: row.trust_level || 'medium', valid_from: row.valid_from || '', valid_until: row.valid_until || '', source_system: row.source_system || '', business_tags: (row.business_tags || []).join(', ') }
    editDialogOpen.value = true
    if (auth.activeSpaceId) members.value = (await fetchSpaceMembers(auth.activeSpaceId)).items
  }

  /** 保存治理字段并刷新列表，服务端负责权限与有效期校验。 */
  async function saveGovernance(payload: KnowledgeBaseForm): Promise<void> {
    if (!editingRow.value) return
    editSaving.value = true
    try {
      await updateKnowledgeBaseGovernance(editingRow.value.id, { business_scenario: payload.business_scenario || '', target_users: payload.target_users || '', owner_user_id: payload.owner_user_id || null, trust_level: payload.trust_level || 'medium', valid_from: payload.valid_from || null, valid_until: payload.valid_until || null, source_system: payload.source_system || '', business_tags: (payload.business_tags || '').split(BUSINESS_TAG_SEPARATOR).map((tag) => tag.trim()).filter(Boolean) })
      editDialogOpen.value = false
      toast.success('治理元数据已更新')
      await loadData()
    } catch (cause) { toast.error(cause instanceof Error ? cause.message : '治理元数据更新失败')
    } finally { editSaving.value = false }
  }

  /** 提交创建请求，成功后刷新列表；失败时保留表单以便修正或重试。 */
  async function saveKnowledgeBase(payload: KnowledgeBaseForm): Promise<void> {
    saving.value = true
    try {
      await createKnowledgeBase({
        ...payload,
        tenant_id: Number(payload.tenant_id),
        owner_user_id: payload.owner_user_id ? Number(payload.owner_user_id) : null,
        valid_from: payload.valid_from || null,
        valid_until: payload.valid_until || null,
        business_tags: (payload.business_tags ?? '')
          .split(BUSINESS_TAG_SEPARATOR)
          .map((tag) => tag.trim())
          .filter(Boolean),
      })
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
    wikiOpen, wikiRow, openWiki,
    editDialogOpen, editSaving, editingRow, members, editForm, openGovernanceDialog, saveGovernance,
  }
}
