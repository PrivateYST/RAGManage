/** 治理编辑弹窗的输入契约，父页面拥有保存与关闭状态。 */
import type { KnowledgeBaseForm } from '../../type'
import type { SpaceMember } from '@/api/members'
export interface GovernanceDialogProps {
  form: KnowledgeBaseForm
  members: SpaceMember[]
  saving: boolean
  name: string
}
