/** 文档表格组件契约：页面传入已筛选文档和当前忙碌文档标识。 */
import type { DocumentRow } from '@/api/documents'

/** 子组件只发出意图事件，生命周期请求和确认流程由页面处理。 */
export interface DocumentTableProps {
  documents: DocumentRow[]
  busyId: string | null
}

/** 表格操作事件由父页面连接到详情或确认弹窗。 */
export interface DocumentTableEmits {
  preview: [document: DocumentRow]
  disable: [document: DocumentRow]
  remove: [document: DocumentRow]
}
