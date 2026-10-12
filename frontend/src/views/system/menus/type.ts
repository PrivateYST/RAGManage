/** 菜单创建与编辑表单使用的页面局部数据契约。 */
export interface MenuForm {
  name: string
  parent_id: string
  sort_order: number
  status: 'active' | 'disabled'
}

/** 创建节点支持目录、页面与按钮三类菜单节点。 */
export interface CreateMenuForm {
  code: string
  name: string
  kind: 'directory' | 'menu' | 'button'
  parent_id: string
  route: string
  icon: string
  permission_code: string
  sort_order: number
  visible: boolean
}
