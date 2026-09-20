import type { KnowledgeBaseRow } from '@/api/admin'
import type {
  KnowledgeBaseMember,
  KnowledgeBaseMemberCandidate,
  KnowledgeBaseRoleCode,
} from '@/api/members'
import type { AddKnowledgeBaseGrantInput } from '@/views/members/type'

export interface KnowledgeBaseAccessPanelProps {
  knowledgeBases: KnowledgeBaseRow[]
  selectedKnowledgeBaseId: string
  members: KnowledgeBaseMember[]
  candidates: KnowledgeBaseMemberCandidate[]
  loading: boolean
  busyId: string
}

export interface KnowledgeBaseAccessPanelEmits {
  (event: 'update:selectedKnowledgeBaseId', value: string): void
  (event: 'addGrant', input: AddKnowledgeBaseGrantInput): void
  (event: 'changeRole', member: KnowledgeBaseMember, roleCode: KnowledgeBaseRoleCode): void
  (event: 'toggleStatus', member: KnowledgeBaseMember): void
}
