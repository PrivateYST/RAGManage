/** LLM Wiki API：集中定义词条内容、受控生命周期和原文选择契约。 */
import { apiRequest } from './client'

/** 审核生命周期；编辑已发布内容后服务端强制回到草稿。 */
export type WikiStatus = 'draft' | 'review' | 'published' | 'retired'

/** 由后端验证并从切片推导的来源，不允许客户端自行拼装文档/版本。 */
export interface WikiSource {
  chunk_id: string
  document_id: string
  document_version_id: string
  document_title: string
  version_no: number
  locator: Record<string, number>
  content: string
  note?: string
}

/** LLM Wiki 词条的审核与证据关联摘要。 */
export interface WikiEntry {
  id: string
  knowledge_base_id: string
  term: string
  definition: string
  status: WikiStatus
  version_no: number
  owner_user_id: string | null
  valid_from: string | null
  valid_until: string | null
  aliases: string[]
  sources: WikiSource[]
  updated_at: string
}

/** 完整内容替换请求；版本号是编辑冲突保护条件。 */
export interface WikiPayload {
  term: string
  definition: string
  aliases: string[]
  owner_user_id: number | null
  valid_from: string | null
  valid_until: string | null
  sources: Array<{ chunk_id: number; note: string }>
  expected_version?: number
}

/** 不可变的历史内容快照。 */
export interface WikiRevision {
  version_no: number
  action: string
  actor_id: string
  created_at: string
  snapshot: WikiEntry
}

/** 只返回当前库内可选择的负责人和已发布原文。 */
export interface WikiOptions {
  members: Array<{ id: string; display_name: string }>
  sources: WikiSource[]
  documents?: Array<{ id: string; title: string }>
}

/** 读取知识库词条，只有当前用户可访问的知识库会返回结果。 */
export function fetchWikiEntries(
  knowledgeBaseId: string,
): Promise<{ items: WikiEntry[]; can_manage: boolean }> {
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/wiki-entries`)
}

/** 创建词条草稿，并保留可追溯的文档/切片来源。 */
export function createWikiEntry(knowledgeBaseId: string, payload: WikiPayload): Promise<WikiEntry> {
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/wiki-entries`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 更新词条内容；状态变更使用独立发布接口。 */
export function updateWikiEntry(id: string, payload: WikiPayload): Promise<WikiEntry> {
  return apiRequest(`/api/v1/wiki-entries/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

/** 使用版本条件推进审核状态，拒绝旧页面重复操作。 */
export function transitionWikiEntry(entry: WikiEntry, status: WikiStatus): Promise<WikiEntry> {
  return apiRequest(`/api/v1/wiki-entries/${encodeURIComponent(entry.id)}/status`, {
    method: 'POST',
    body: JSON.stringify({ status, expected_version: entry.version_no }),
  })
}

/** 搜索当前发布原文的证据切片，避免用户手填内部编号。 */
export function fetchWikiOptions(id: string, query = ''): Promise<WikiOptions> {
  return apiRequest(
    `/api/v1/knowledge-bases/${encodeURIComponent(id)}/wiki-options?query=${encodeURIComponent(query)}&limit=100`,
  )
}

/** 获取管理权限下的完整修订历史。 */
export function fetchWikiRevisions(id: string): Promise<{ items: WikiRevision[] }> {
  return apiRequest(`/api/v1/wiki-entries/${encodeURIComponent(id)}/revisions`)
}

/** 可追溯的章节候选，existing 表示已存在同概念词条，不重复导入。 */
export interface WikiCandidate {
  key: string
  term: string
  definition: string
  aliases: string[]
  sources: WikiSource[]
  warning: string
  existing: boolean
}

/** 预览所依据的发布快照，导入时必须带回并由后端重新校验。 */
export interface WikiExtractionPreview {
  release_id: string
  document_version_id: string
  document_title: string
  method: string
  notice: string
  items: WikiCandidate[]
}

/** 对一份已发布文档按明确章节生成候选，预览不会写入知识库。 */
export function previewWikiExtraction(
  kb: string,
  documentId: string,
): Promise<WikiExtractionPreview> {
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(kb)}/wiki-extraction-preview`, {
    method: 'POST',
    body: JSON.stringify({ document_id: Number(documentId) }),
  })
}

/** 导入选中候选为草稿；后台重建候选，版本变化时拒绝旧预览。 */
export function importWikiExtraction(
  kb: string,
  payload: {
    document_id: number
    release_id: number
    document_version_id: number
    candidate_keys: string[]
    owner_user_id: number | null
  },
): Promise<{ items: WikiEntry[]; skipped: string[] }> {
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(kb)}/wiki-extraction-import`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
