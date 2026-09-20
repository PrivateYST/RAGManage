import { apiRequest } from './client'

export type SpaceRoleCode = 'space_admin' | 'space_member' | 'customer_reader'
export type KnowledgeBaseRoleCode = 'kb_admin' | 'editor' | 'reader'
export type MembershipStatus = 'active' | 'disabled'

export interface SpaceMember {
  id: string
  login: string
  display_name: string
  user_status: MembershipStatus
  status: MembershipStatus
  role_code: SpaceRoleCode
  role_name?: string
  knowledge_base_count: number
  created_at?: string
}

export interface KnowledgeBaseMember {
  id: string
  login: string
  display_name: string
  space_status?: MembershipStatus
  space_role_code?: SpaceRoleCode
  status: MembershipStatus
  role_code: KnowledgeBaseRoleCode
  role_name?: string
  created_at?: string
}

export interface KnowledgeBaseMemberCandidate {
  id: string
  login: string
  display_name: string
  grant_status: MembershipStatus | null
  grant_role_code: KnowledgeBaseRoleCode | null
}

export interface MembershipAuditItem {
  id: string
  action: string
  target_type: string
  target_id: string | null
  actor_name: string | null
  target_name: string | null
  change_summary: Record<string, unknown>
  created_at: string
}

export function fetchSpaceMembers(spaceId: string): Promise<{ items: SpaceMember[] }> {
  return apiRequest(`/api/v1/spaces/${spaceId}/members`)
}

export function addSpaceMember(
  spaceId: string,
  payload: { login: string; role_code: SpaceRoleCode },
): Promise<SpaceMember> {
  return apiRequest(`/api/v1/spaces/${spaceId}/members`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateSpaceMember(
  spaceId: string,
  userId: string,
  payload: { role_code?: SpaceRoleCode; status?: MembershipStatus },
): Promise<SpaceMember> {
  return apiRequest(`/api/v1/spaces/${spaceId}/members/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function fetchKnowledgeBaseMembers(
  knowledgeBaseId: string,
): Promise<{ items: KnowledgeBaseMember[] }> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/members`)
}

export function fetchKnowledgeBaseMemberCandidates(
  knowledgeBaseId: string,
): Promise<{ items: KnowledgeBaseMemberCandidate[] }> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/member-candidates`)
}

export function addKnowledgeBaseMember(
  knowledgeBaseId: string,
  payload: { user_id: number; role_code: KnowledgeBaseRoleCode },
): Promise<KnowledgeBaseMember> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/members`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function updateKnowledgeBaseMember(
  knowledgeBaseId: string,
  userId: string,
  payload: { role_code?: KnowledgeBaseRoleCode; status?: MembershipStatus },
): Promise<KnowledgeBaseMember> {
  return apiRequest(`/api/v1/knowledge-bases/${knowledgeBaseId}/members/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function fetchMembershipAudit(spaceId: string): Promise<{ items: MembershipAuditItem[] }> {
  return apiRequest(`/api/v1/spaces/${spaceId}/membership-audit`)
}
