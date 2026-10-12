import type { CreateMenuForm } from '../../type'
/** 新建菜单弹窗的节点集合和异步状态。 */
import type { MenuRow } from '@/api/admin'

export interface MenuCreateDialogProps {
  open: boolean
  menus: MenuRow[]
  submitting: boolean
}

export interface MenuCreateDialogEmits {
  close: []
  submit: [form: CreateMenuForm]
}
