/** 新建用户弹窗的外部数据与成功事件契约。 */
import type { TenantRow } from '@/api/admin'

export interface CreateUserDialogProps {
  open: boolean
  tenants: TenantRow[]
}

export interface CreateUserDialogEmits {
  close: []
  created: []
}
