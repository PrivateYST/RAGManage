/** 操作日志筛选栏的受控输入契约。 */

import type { AuditScope } from '../../type'

/** 当前范围、筛选条件及平台角色决定筛选栏可展示的选项。 */
export interface AuditFiltersProps {
  scope: AuditScope
  actionPrefix: string
  actor: string
  targetType: string
  spaceName: string
  isPlatformAdmin: boolean
  loading: boolean
}

/** 子组件只发出输入更新和用户意图，查询请求由页面执行。 */
export interface AuditFiltersEmits {
  (event: 'update:scope', value: AuditScope): void
  (event: 'update:actionPrefix', value: string): void
  (event: 'update:actor', value: string): void
  (event: 'update:targetType', value: string): void
  (event: 'submit'): void
  (event: 'reset'): void
}
