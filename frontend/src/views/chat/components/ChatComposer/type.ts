/** 输入区展示当前生成状态，并将发送和停止意图上报给页面。 */
export interface ChatComposerProps {
  sending: boolean
  canSend: boolean
  disabledReason: string
}

/** 输入区上报给工作区的发送与停止意图。 */
export interface ChatComposerEmits {
  send: []
  stop: []
}
