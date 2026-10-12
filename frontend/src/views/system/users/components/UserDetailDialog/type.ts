/** 用户详情弹窗的输入属性；用户基础资料用于标题和请求 ID。 */
import type { UserRow } from '@/api/admin'

export interface UserDetailDialogProps {
  open: boolean
  user: UserRow | null
}
