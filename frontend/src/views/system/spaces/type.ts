/** 客户空间页面专属表单与状态类型。 */
export interface CreateSpaceForm {
  code: string
  name: string
}

/** 新建空间弹窗对外暴露的输入与事件契约。 */
export interface CreateSpaceDialogProps {
  open: boolean
  saving: boolean
}
