/** 文档管理页面类型：集中声明生命周期操作和知识库用途展示映射。 */
import type { DocumentRow } from '@/api/documents'

/** 停用和删除必须先进入确认状态，避免列表操作直接修改服务端数据。 */
export interface PendingDocumentAction {
  document: DocumentRow
  action: 'disable' | 'remove'
}

/** 页面以中文标签展示知识库用途，未知服务端值仍由模板回退原文。 */
export type KnowledgeBasePurposeLabels = Record<string, string>
