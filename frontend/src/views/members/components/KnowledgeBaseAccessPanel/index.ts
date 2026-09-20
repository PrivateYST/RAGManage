import type { KnowledgeBaseMemberCandidate, KnowledgeBaseRoleCode } from '@/api/members'
import type { KnowledgeBaseAccessPanelEmits, KnowledgeBaseAccessPanelProps } from './type'
import { computed, shallowRef, toRef } from 'vue'
import { KNOWLEDGE_BASE_ROLE_LABELS } from '@/views/members/enum'

export const knowledgeBaseRoleOptions = Object.entries(KNOWLEDGE_BASE_ROLE_LABELS) as [
  KnowledgeBaseRoleCode,
  string,
][]

export function useKnowledgeBaseAccessPanel(
  props: KnowledgeBaseAccessPanelProps,
  emit: KnowledgeBaseAccessPanelEmits,
) {
  const candidateId = shallowRef('')
  const roleCode = shallowRef<KnowledgeBaseRoleCode>('reader')
  const candidates = toRef(props, 'candidates')
  const availableCandidates = computed(() =>
    candidates.value.filter((item) => item.grant_status !== 'active'),
  )
  const selectedCandidate = computed<KnowledgeBaseMemberCandidate | null>(
    () => candidates.value.find((item) => item.id === candidateId.value) ?? null,
  )

  function submitGrant(): void {
    if (!candidateId.value) return
    emit('addGrant', { userId: candidateId.value, roleCode: roleCode.value })
    candidateId.value = ''
    roleCode.value = 'reader'
  }

  return { candidateId, roleCode, availableCandidates, selectedCandidate, submitGrant }
}
