/** 新建空间表单的局部状态类型。 */
export interface CreateSpaceForm {
  code: string
  name: string
}

/** 父级页面提供的显示状态和异步提交状态。 */
export interface CreateSpaceDialogProps {
  open: boolean
  saving: boolean
}
