import type { AddKnowledgeBaseGrantInput, AddSpaceMemberInput, MemberView } from './type'
import type { KnowledgeBaseRow } from '@/api/admin'
import type {
  KnowledgeBaseMember,
  KnowledgeBaseMemberCandidate,
  KnowledgeBaseRoleCode,
  MembershipAuditItem,
  SpaceMember,
  SpaceRoleCode,
} from '@/api/members'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '@/api/admin'
import {
  addKnowledgeBaseMember,
  addSpaceMember,
  fetchKnowledgeBaseMemberCandidates,
  fetchKnowledgeBaseMembers,
  fetchMembershipAudit,
  fetchSpaceMembers,
  updateKnowledgeBaseMember,
  updateSpaceMember,
} from '@/api/members'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

type PendingStatusAction =
  | { kind: 'space'; member: SpaceMember; busyId: string }
  | { kind: 'knowledge'; member: KnowledgeBaseMember; busyId: string }

export function useMembersPage() {
  const auth = useAuthStore()
  const toast = useAppToast()
  const view = shallowRef<MemberView>('space')
  const loading = shallowRef(false)
  const grantLoading = shallowRef(false)
  const busyId = shallowRef('')
  const addDialogOpen = shallowRef(false)
  const spaceMembers = ref<SpaceMember[]>([])
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const knowledgeBaseMembers = ref<KnowledgeBaseMember[]>([])
  const candidates = ref<KnowledgeBaseMemberCandidate[]>([])
  const auditItems = ref<MembershipAuditItem[]>([])
  const selectedKnowledgeBaseId = shallowRef('')
  const pendingStatus = shallowRef<PendingStatusAction | null>(null)

  const canManageSpace = computed(() => auth.activeSpace?.role === 'space_admin')
  const activeMembers = computed(() =>
    spaceMembers.value.filter((item) => item.status === 'active'),
  )
  const stats = computed(() => ({
    active: activeMembers.value.length,
    admins: activeMembers.value.filter((item) => item.role_code === 'space_admin').length,
    customers: activeMembers.value.filter((item) => item.role_code === 'customer_reader').length,
    grants: activeMembers.value.reduce((total, item) => total + item.knowledge_base_count, 0),
  }))

  async function loadPage(): Promise<void> {
    loading.value = true
    knowledgeBaseMembers.value = []
    candidates.value = []
    const spaceId = auth.activeSpaceId
    if (!spaceId) {
      spaceMembers.value = []
      knowledgeBases.value = []
      auditItems.value = []
      loading.value = false
      return
    }
    try {
      const requests: [
        Promise<{ items: KnowledgeBaseRow[] }>,
        Promise<{ items: SpaceMember[] }> | null,
        Promise<{ items: MembershipAuditItem[] }> | null,
      ] = [
        fetchKnowledgeBases(spaceId),
        canManageSpace.value ? fetchSpaceMembers(spaceId) : null,
        canManageSpace.value ? fetchMembershipAudit(spaceId) : null,
      ]
      const [knowledgeBaseResult, memberResult, auditResult] = await Promise.all(
        requests.map((item) => item ?? Promise.resolve({ items: [] })),
      )
      knowledgeBases.value = knowledgeBaseResult.items as KnowledgeBaseRow[]
      spaceMembers.value = memberResult.items as SpaceMember[]
      auditItems.value = auditResult.items as MembershipAuditItem[]
      if (!knowledgeBases.value.some((item) => item.id === selectedKnowledgeBaseId.value))
        selectedKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? ''
      if (!canManageSpace.value) view.value = 'knowledge'
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '成员信息加载失败')
    } finally {
      loading.value = false
    }
  }

  async function loadKnowledgeBaseAccess(): Promise<void> {
    knowledgeBaseMembers.value = []
    candidates.value = []
    if (!selectedKnowledgeBaseId.value) return
    grantLoading.value = true
    try {
      const [membersResult, candidatesResult] = await Promise.all([
        fetchKnowledgeBaseMembers(selectedKnowledgeBaseId.value),
        fetchKnowledgeBaseMemberCandidates(selectedKnowledgeBaseId.value),
      ])
      knowledgeBaseMembers.value = membersResult.items
      candidates.value = candidatesResult.items
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '知识库授权加载失败')
    } finally {
      grantLoading.value = false
    }
  }

  async function refreshAudit(): Promise<void> {
    if (!auth.activeSpaceId || !canManageSpace.value) return
    auditItems.value = (await fetchMembershipAudit(auth.activeSpaceId)).items
  }

  async function submitSpaceMember(input: AddSpaceMemberInput): Promise<boolean> {
    if (!auth.activeSpaceId) return false
    try {
      await addSpaceMember(auth.activeSpaceId, { login: input.login, role_code: input.roleCode })
      toast.success('成员已加入当前空间')
      await Promise.all([loadSpaceMembers(), refreshAudit()])
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '添加成员失败')
      return false
    }
  }

  async function loadSpaceMembers(): Promise<void> {
    if (auth.activeSpaceId && canManageSpace.value)
      spaceMembers.value = (await fetchSpaceMembers(auth.activeSpaceId)).items
  }

  async function changeSpaceRole(member: SpaceMember, roleCode: SpaceRoleCode): Promise<void> {
    if (!auth.activeSpaceId || member.role_code === roleCode) return
    busyId.value = `space-${member.id}`
    try {
      await updateSpaceMember(auth.activeSpaceId, member.id, { role_code: roleCode })
      toast.success('空间角色已更新')
      await Promise.all([loadSpaceMembers(), refreshAudit()])
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '空间角色更新失败')
    } finally {
      busyId.value = ''
    }
  }

  /** 停用空间成员会立即撤销其访问权，先打开确认框；恢复成员可以直接执行。 */
  async function toggleSpaceStatus(member: SpaceMember): Promise<void> {
    if (member.status === 'active') {
      pendingStatus.value = { kind: 'space', member, busyId: `space-${member.id}` }
      return
    }
    await updateSpaceStatus(member)
  }

  /** 执行空间成员状态变更，并同步刷新成员和审计列表。 */
  async function updateSpaceStatus(member: SpaceMember): Promise<boolean> {
    if (!auth.activeSpaceId) return false
    busyId.value = `space-${member.id}`
    try {
      const status = member.status === 'active' ? 'disabled' : 'active'
      await updateSpaceMember(auth.activeSpaceId, member.id, { status })
      toast.success(status === 'active' ? '成员已恢复' : '成员已停用')
      await Promise.all([loadSpaceMembers(), refreshAudit()])
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '成员状态更新失败')
      return false
    } finally {
      busyId.value = ''
    }
  }

  /** 知识库授权状态变更同样先经过确认，避免误撤销访问权限。 */
  async function toggleKnowledgeBaseStatus(member: KnowledgeBaseMember): Promise<void> {
    if (member.status === 'active') {
      pendingStatus.value = { kind: 'knowledge', member, busyId: `grant-${member.id}` }
      return
    }
    await updateKnowledgeBaseStatus(member)
  }

  /** 执行知识库授权状态变更，并刷新授权、审计和成员统计。 */
  async function updateKnowledgeBaseStatus(member: KnowledgeBaseMember): Promise<boolean> {
    if (!selectedKnowledgeBaseId.value) return false
    busyId.value = `grant-${member.id}`
    try {
      const status = member.status === 'active' ? 'disabled' : 'active'
      await updateKnowledgeBaseMember(selectedKnowledgeBaseId.value, member.id, { status })
      toast.success(status === 'active' ? '知识库授权已恢复' : '知识库授权已撤销')
      await Promise.all([loadKnowledgeBaseAccess(), refreshAudit(), loadSpaceMembers()])
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '知识库授权状态更新失败')
      return false
    } finally {
      busyId.value = ''
    }
  }

  /** 关闭成员状态确认框，不修改服务端状态。 */
  function cancelPendingStatus(): void {
    if (!busyId.value) pendingStatus.value = null
  }

  /** 确认当前成员停用/授权撤销操作。 */
  async function confirmPendingStatus(): Promise<void> {
    const pending = pendingStatus.value
    if (!pending) return
    const updated =
      pending.kind === 'space'
        ? await updateSpaceStatus(pending.member)
        : await updateKnowledgeBaseStatus(pending.member)
    if (updated) pendingStatus.value = null
  }

  async function submitKnowledgeBaseGrant(input: AddKnowledgeBaseGrantInput): Promise<void> {
    if (!selectedKnowledgeBaseId.value) return
    busyId.value = `grant-${input.userId}`
    try {
      const candidate = candidates.value.find((item) => item.id === input.userId)
      if (candidate?.grant_status) {
        await updateKnowledgeBaseMember(selectedKnowledgeBaseId.value, input.userId, {
          role_code: input.roleCode,
          status: 'active',
        })
      } else {
        await addKnowledgeBaseMember(selectedKnowledgeBaseId.value, {
          user_id: Number(input.userId),
          role_code: input.roleCode,
        })
      }
      toast.success(candidate?.grant_status ? '知识库授权已恢复' : '知识库授权已添加')
      await Promise.all([loadKnowledgeBaseAccess(), refreshAudit(), loadSpaceMembers()])
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '知识库授权失败')
    } finally {
      busyId.value = ''
    }
  }

  async function changeKnowledgeBaseRole(
    member: KnowledgeBaseMember,
    roleCode: KnowledgeBaseRoleCode,
  ): Promise<void> {
    if (!selectedKnowledgeBaseId.value || member.role_code === roleCode) return
    busyId.value = `grant-${member.id}`
    try {
      await updateKnowledgeBaseMember(selectedKnowledgeBaseId.value, member.id, {
        role_code: roleCode,
      })
      toast.success('知识库角色已更新')
      await Promise.all([loadKnowledgeBaseAccess(), refreshAudit()])
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '知识库角色更新失败')
    } finally {
      busyId.value = ''
    }
  }

  watch(() => auth.activeSpaceId, loadPage, { immediate: true })
  watch(selectedKnowledgeBaseId, loadKnowledgeBaseAccess)

  return {
    auth,
    view,
    loading,
    grantLoading,
    busyId,
    addDialogOpen,
    spaceMembers,
    knowledgeBases,
    knowledgeBaseMembers,
    candidates,
    auditItems,
    selectedKnowledgeBaseId,
    pendingStatus,
    canManageSpace,
    stats,
    loadPage,
    submitSpaceMember,
    changeSpaceRole,
    toggleSpaceStatus,
    submitKnowledgeBaseGrant,
    changeKnowledgeBaseRole,
    toggleKnowledgeBaseStatus,
    cancelPendingStatus,
    confirmPendingStatus,
  }
}
