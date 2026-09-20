/** 审计详情弹窗的纯展示转换函数。 */

import type { AuditLogItem } from '@/api/audit'
import { auditActionLabel, auditTargetLabel } from '@/views/audit/enum'

/** 将服务端时间转换为用户本地的 24 小时制展示。 */
export function formatAuditTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

/** 以稳定缩进展示完整变更摘要，便于管理员核查字段。 */
export function auditSummaryJson(item: AuditLogItem): string {
  return JSON.stringify(item.change_summary, null, 2)
}

export { auditActionLabel, auditTargetLabel }
