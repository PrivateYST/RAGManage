/** 编辑弹窗仅接收当前账号，并通过 v-model 与父页面同步开关状态。 */
import type { TenantRow, UserRow } from '@/api/admin'

export interface EditUserDialogProps {
  open: boolean
  user: UserRow | null
  tenants: TenantRow[]
}

export interface EditUserDialogEmits {
  'update:open': [open: boolean]
  saved: []
}
