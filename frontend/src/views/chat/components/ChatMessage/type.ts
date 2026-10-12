/** 单条问答消息的 Props 与用户操作事件契约。 */
import type { ChatMessageRow } from '@/api/chat'

/** 单条消息内容、状态及可用操作。 */
export interface ChatMessageProps {
  message: ChatMessageRow
  busy: boolean
}

/** 消息模板向工作区上报的用户意图。 */
export interface ChatMessageEmits {
  citations: [message: ChatMessageRow]
  retry: [message: ChatMessageRow]
  resume: [message: ChatMessageRow]
  feedback: [message: ChatMessageRow, rating: 'helpful' | 'not_helpful']
}
