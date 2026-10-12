import type { KnowledgeBaseRow } from '@/api/admin'

/** 检索表单接收的外部数据与可用状态。 */
export interface SearchQueryFormProps {
  knowledgeBases: KnowledgeBaseRow[]
  loading: boolean
  searching: boolean
  canSearch: boolean
}
