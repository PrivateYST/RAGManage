import type { KnowledgeBaseRoleCode, SpaceRoleCode } from '../../api/members'

export const SPACE_ROLE_LABELS: Record<SpaceRoleCode, string> = {
  space_admin: '空间管理员',
  space_member: '空间成员',
  customer_reader: '客户用户',
}

export const KNOWLEDGE_BASE_ROLE_LABELS: Record<KnowledgeBaseRoleCode, string> = {
  kb_admin: '知识库管理员',
  editor: '编辑者',
  reader: '读者',
}
