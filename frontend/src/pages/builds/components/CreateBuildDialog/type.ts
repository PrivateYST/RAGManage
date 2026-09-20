import type { KnowledgeBaseRow } from '../../../../api/admin'

export interface CreateBuildDialogProps {
  open: boolean
  knowledgeBases: KnowledgeBaseRow[]
  initialKnowledgeBaseId: string
  creating: boolean
}

export interface CreateBuildDialogActions {
  close: () => void
  confirm: (knowledgeBaseId: string) => void
}
