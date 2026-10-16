/** 词条列表只展示与上报操作意图，权限来自后端返回值。 */
import type { WikiEntry } from '@/api/wiki'
export interface WikiEntryListProps {
  entries: WikiEntry[]
  canManage: boolean
  busy: boolean
}
