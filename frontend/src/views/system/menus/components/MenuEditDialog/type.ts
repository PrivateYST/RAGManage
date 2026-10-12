import type { MenuForm } from '../../type'
/** 编辑菜单弹窗输入契约；路由和权限标识仅用于明确对象，不允许编辑。 */
import type { MenuRow } from '@/api/admin'

export interface MenuEditDialogProps {
  menu: MenuRow | null
  menus: MenuRow[]
  submitting: boolean
}

export interface MenuEditDialogEmits {
  close: []
  submit: [form: MenuForm]
}
