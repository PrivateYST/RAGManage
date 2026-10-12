/** 将输入区提交与停止交互转成具名动作，模板只负责绑定事件。 */
export function useChatComposer(send: () => void, stopGeneration: () => void) {
  function submit(): void {
    send()
  }

  function stop(): void {
    stopGeneration()
  }

  return { submit, stop }
}
