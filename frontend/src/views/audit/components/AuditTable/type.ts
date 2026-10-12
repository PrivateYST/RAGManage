/** 操作日志表格的展示与交互契约。 */

import type { AuditLogItem } from '@/api/audit'

export interface AuditTableProps {
  items: AuditLogItem[]
  loading: boolean
  loadingMore: boolean
  nextCursor: string | null
  scope: 'space' | 'platform'
}

export interface AuditTableEmits {
  (event: 'select', item: AuditLogItem): void
  (event: 'loadMore'): void
}
