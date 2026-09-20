const ACTION_LABELS: Record<string, string> = {
  'space_member.add': '添加空间成员',
  'space_member.update': '修改空间成员',
  'space_member.disable': '停用空间成员',
  'knowledge_base_member.add': '添加知识库授权',
  'knowledge_base_member.update': '修改知识库授权',
  'knowledge_base_member.revoke': '撤销知识库授权',
}

export function actionLabel(action: string): string {
  return ACTION_LABELS[action] ?? action
}

export function summaryText(summary: Record<string, unknown>): string {
  const after = summary.after as Record<string, unknown> | undefined
  const role = String(after?.role_code ?? summary.role_code ?? '')
  const status = String(after?.status ?? summary.status ?? '')
  const knowledgeBaseId = summary.knowledge_base_id ? `知识库 #${summary.knowledge_base_id}` : ''
  return [knowledgeBaseId, role, status].filter(Boolean).join(' · ') || '成员授权已更新'
}
