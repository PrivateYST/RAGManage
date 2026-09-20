/** 操作日志页面的筛选状态与选择状态类型。 */

import type { AuditLogItem } from '../../api/audit'

/** 日志查询范围：当前显式授权空间或平台级配置。 */
export type AuditScope = 'space' | 'platform'

/** 页面持有的组合筛选条件。 */
export interface AuditFilterState {
  scope: AuditScope
  actionPrefix: string
  actor: string
  targetType: string
}

/** 当前打开详情的事件；null 表示详情弹窗关闭。 */
export type SelectedAuditLog = AuditLogItem | null
