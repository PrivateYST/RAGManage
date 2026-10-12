/** 回答引用侧栏的 Props 与关闭事件契约。 */
import type { Citation } from '@/api/chat'

/** 引用抽屉接收的引用集合及显示状态。 */
export interface CitationPanelProps {
  open: boolean
  citations: Citation[]
}

/** 引用面板上报的关闭意图。 */
export interface CitationPanelEmits {
  close: []
}
