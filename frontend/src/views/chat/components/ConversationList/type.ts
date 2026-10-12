/** 会话列表的数据边界与上报事件契约。 */
import type { ConversationRow } from '@/api/chat'

/** 会话列表所需数据、当前项和操作禁用状态。 */
export interface ConversationListProps {
  conversations: ConversationRow[]
  activeId: string
  disabled: boolean
}

/** 会话列表上报给工作区的操作。 */
export interface ConversationListEmits {
  select: [conversationId: string]
  create: []
  delete: [conversationId: string]
}
