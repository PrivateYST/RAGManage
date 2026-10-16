/** 词条表单仅编辑完整内容，审核状态由列表独立处理。 */
import type { WikiOptions } from '@/api/wiki'
export interface WikiEntryFormProps {
  options: WikiOptions
  editing: boolean
  busy: boolean
  searching: boolean
}
