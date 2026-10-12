/** 消息展示状态和回答结果标签的组件逻辑模块。 */
import type { ChatMessageRow } from '@/api/chat'

/** 提供单条消息的状态和回答结果展示标签。 */
export function useChatMessage() {
  function stateLabel(value: ChatMessageRow): string {
    if (value.hidden) return '来源权限已失效，回答已隐藏'
    return (
      { pending: '等待生成', generating: '正在生成', failed: '生成失败', cancelled: '已停止' }[
        value.state
      ] ?? ''
    )
  }

  function outcomeLabel(value: ChatMessageRow): string {
    if (!value.outcome) return ''
    return {
      answered: '已回答',
      no_answer: '未找到依据',
      source_conflict: '来源冲突',
      index_not_ready: '索引未就绪',
    }[value.outcome]
  }

  return { stateLabel, outcomeLabel }
}
