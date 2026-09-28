import { apiRequest } from './client'

export type ParseStatus =
  'queued' | 'processing' | 'complete' | 'partial' | 'unsupported' | 'failed'

export interface DocumentRow {
  id: string
  title: string
  status: 'active' | 'disabled' | 'deleted'
  created_at: string
  updated_at: string
  version_id: string | null
  version_no: number | null
  parse_status: ParseStatus | null
  file_size: number | null
  mime_type: string | null
  version_created_at: string | null
  published: boolean
}

export interface DocumentVersion {
  id: string
  version_no: number
  sha256: string
  mime_type: string
  file_size: number
  parse_status: ParseStatus
  warnings: string[]
  created_at: string
}

export interface DocumentDetail {
  document: {
    id: string
    title: string
    status: DocumentRow['status']
    tenant_id: string
    knowledge_base_id: string
  }
  versions: DocumentVersion[]
}

/** 两个文档版本的切片级差异汇总。 */
export interface DocumentVersionDiff {
  document: { id: string; title: string }
  before: { id: string; version_no: number }
  after: { id: string; version_no: number }
  diff: {
    before_chunk_count: number
    after_chunk_count: number
    added_chunks: number
    removed_chunks: number
    changed_chunks: number
    changes: Array<{
      kind: 'added' | 'removed' | 'changed'
      before_ordinals: number[]
      after_ordinals: number[]
      before_preview: string[]
      after_preview: string[]
    }>
  }
}

export interface TaskRow {
  id: string
  tenant_id: string
  knowledge_base_id: string | null
  task_type: string
  state: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled' | 'interrupted'
  attempt: number
  error: Record<string, unknown> | null
  created_at: string
  updated_at: string
  item_count: number
  completed_items: number
}

export interface UploadResult {
  document: { id: string; title: string }
  version: { id: string; version_no: number; parse_status: ParseStatus; created_at: string }
  task: { id: string; state: TaskRow['state']; task_type: string; created_at: string }
}

export interface ChunkRow {
  id: string
  ordinal: number
  content: string
  section_path: string[]
  locator: Record<string, number>
  token_count: number
  artifact_state?: string
}

export function fetchDocuments(
  knowledgeBaseId: string,
): Promise<{ items: DocumentRow[]; knowledge_base: { id: string; name: string } }> {
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents`)
}

export function uploadDocument(knowledgeBaseId: string, file: File): Promise<UploadResult> {
  const body = new FormData()
  body.append('file', file)
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/documents`, {
    method: 'POST',
    body,
  })
}

export function fetchDocument(documentId: string): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(`/api/v1/documents/${encodeURIComponent(documentId)}`)
}

export function fetchVersionPreview(versionId: string): Promise<{
  document: { id: string; title: string }
  version: Pick<DocumentVersion, 'id' | 'version_no' | 'parse_status' | 'warnings'>
  chunks: ChunkRow[]
}> {
  return apiRequest(`/api/v1/document-versions/${encodeURIComponent(versionId)}/preview`)
}

/** 返回受权限保护的原文件下载地址；浏览器会携带当前 Session Cookie。 */
export function documentVersionDownloadUrl(versionId: string): string {
  return `/api/v1/document-versions/${encodeURIComponent(versionId)}/download`
}

/** 获取同一文档两个版本的切片差异。 */
export function compareDocumentVersions(
  documentId: string,
  beforeVersionId: string,
  afterVersionId: string,
): Promise<DocumentVersionDiff> {
  const query = new URLSearchParams({
    before_version_id: beforeVersionId,
    after_version_id: afterVersionId,
  })
  return apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}/compare?${query}`)
}

export function disableDocument(documentId: string): Promise<void> {
  return apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}/disable`, {
    method: 'POST',
  })
}

/** 重新排队文档最新版本解析任务。 */
export function reparseDocument(
  documentId: string,
): Promise<{ task: TaskRow; version_id: string }> {
  return apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}/reparse`, {
    method: 'POST',
  })
}

/** 创建知识库索引构建，重新生成当前内容的嵌入向量。 */
export function rebuildKnowledgeBase(knowledgeBaseId: string): Promise<{ task: TaskRow }> {
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/builds`, {
    method: 'POST',
  })
}

export function deleteDocument(documentId: string): Promise<void> {
  return apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' })
}

export function fetchTasks(
  filters: { tenantId?: string; knowledgeBaseId?: string } = {},
): Promise<{ items: TaskRow[] }> {
  const query = new URLSearchParams()
  if (filters.tenantId) query.set('tenant_id', filters.tenantId)
  if (filters.knowledgeBaseId) query.set('knowledge_base_id', filters.knowledgeBaseId)
  const suffix = query.size ? `?${query.toString()}` : ''
  return apiRequest(`/api/v1/tasks${suffix}`)
}

export function fetchTask(taskId: string): Promise<{
  task: TaskRow
  items: Array<{
    id: string
    target_id: string | null
    stage: string
    state: string
    attempt: number
    error: Record<string, unknown> | null
    updated_at: string
  }>
}> {
  return apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}`)
}

export function retryTask(taskId: string): Promise<TaskRow> {
  return apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' })
}

export function cancelTask(taskId: string): Promise<void> {
  return apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' })
}
