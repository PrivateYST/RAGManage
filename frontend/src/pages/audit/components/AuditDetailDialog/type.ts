/** 审计详情弹窗的输入契约。 */

import type { AuditLogItem } from '../../../../api/audit'

/** 弹窗只接收一条已授权且不可变的审计事件。 */
export interface AuditDetailDialogProps {
  item: AuditLogItem
}
