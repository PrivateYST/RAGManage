/** 操作日志 API 契约，只负责查询参数编码和响应类型，不处理页面状态。 */

import { apiRequest } from './client'

/** 服务端返回的单条不可变审计事件。 */
export interface AuditLogItem {
  id: string
  tenant_id: string | null
  tenant_name: string | null
  actor_id: string | null
  actor_name: string | null
  actor_login: string | null
  action: string
  target_type: string
  target_id: string | null
  change_summary: Record<string, unknown>
  request_id: string | null
  created_at: string
}

/** 使用 ID 游标分页的审计事件响应。 */
export interface AuditLogPage {
  items: AuditLogItem[]
  next_cursor: string | null
}

/** 审计查询筛选条件；tenantId 缺省时表示平台级范围。 */
export interface AuditLogFilters {
  tenantId?: string
  actionPrefix?: string
  actor?: string
  targetType?: string
  cursor?: string
  limit?: number
}

/** 查询授权范围内的审计事件，并把可选筛选条件编码为 URL 参数。 */
export function fetchAuditLogs(filters: AuditLogFilters): Promise<AuditLogPage> {
  const params = new URLSearchParams()
  if (filters.tenantId) params.set('tenant_id', filters.tenantId)
  if (filters.actionPrefix) params.set('action_prefix', filters.actionPrefix)
  if (filters.actor) params.set('actor', filters.actor)
  if (filters.targetType) params.set('target_type', filters.targetType)
  if (filters.cursor) params.set('cursor', filters.cursor)
  params.set('limit', String(filters.limit ?? 30))
  return apiRequest(`/api/v1/audit-logs?${params.toString()}`)
}
