import type { KnowledgeBaseRoleCode, SpaceRoleCode } from '../../api/members'

export type MemberView = 'space' | 'knowledge' | 'audit'

export interface AddSpaceMemberInput {
  login: string
  roleCode: SpaceRoleCode
}

export interface AddKnowledgeBaseGrantInput {
  userId: string
  roleCode: KnowledgeBaseRoleCode
}
