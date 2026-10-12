/** 成员授权历史的只读展示转换，组件不修改审计数据。 */
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

/** 将审计时间转换为管理员熟悉的本地日期时间格式。 */
export function formatAuditDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN')
}
