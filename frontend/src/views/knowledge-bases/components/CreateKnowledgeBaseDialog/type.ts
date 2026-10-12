/** 创建知识库弹窗的数据契约。 */
import type { KnowledgeBaseForm } from '../../type'

/** 弹窗表单通过 submit 事件交由页面提交，避免把 API 请求耦合到展示组件。 */
export interface CreateKnowledgeBaseDialogProps {
  form: KnowledgeBaseForm
  spaceName: string
  saving: boolean
}
