/** 会话管理弹窗通过事件将关闭与当前会话撤销结果交给 AppShell。 */
export interface SessionManagementDialogProps {
  open: boolean
}

export interface SessionManagementDialogEmits {
  (event: 'close'): void
  (event: 'current-session-revoked'): void
}
