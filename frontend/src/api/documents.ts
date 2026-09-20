import { apiRequest } from './client'

export type ParseStatus = 'queued' | 'processing' | 'complete' | 'partial' | 'unsupported' | 'failed'

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
  document: { id: string, title: string }
  version: { id: string, version_no: number, parse_status: ParseStatus, created_at: string }
  task: { id: string, state: TaskRow['state'], task_type: string, created_at: string }
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

export function fetchDocuments(knowledgeBaseId: string): Promise<{ items: DocumentRow[], knowledge_base: { id: string, name: string } }> {
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
  document: { id: string, title: string }
  version: Pick<DocumentVersion, 'id' | 'version_no' | 'parse_status' | 'warnings'>
  chunks: ChunkRow[]
}> {
  return apiRequest(`/api/v1/document-versions/${encodeURIComponent(versionId)}/preview`)
}

export function disableDocument(documentId: string): Promise<void> {
  return apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}/disable`, { method: 'POST' })
}

export function deleteDocument(documentId: string): Promise<void> {
  return apiRequest(`/api/v1/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' })
}

export function fetchTasks(filters: { tenantId?: string, knowledgeBaseId?: string } = {}): Promise<{ items: TaskRow[] }> {
  const query = new URLSearchParams()
  if (filters.tenantId)
    query.set('tenant_id', filters.tenantId)
  if (filters.knowledgeBaseId)
    query.set('knowledge_base_id', filters.knowledgeBaseId)
  const suffix = query.size ? `?${query.toString()}` : ''
  return apiRequest(`/api/v1/tasks${suffix}`)
}

export function fetchTask(taskId: string): Promise<{ task: TaskRow, items: Array<{ id: string, target_id: string | null, stage: string, state: string, attempt: number, error: Record<string, unknown> | null, updated_at: string }> }> {
  return apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}`)
}

export function retryTask(taskId: string): Promise<TaskRow> {
  return apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' })
}

export function cancelTask(taskId: string): Promise<void> {
  return apiRequest(`/api/v1/tasks/${encodeURIComponent(taskId)}/cancel`, { method: 'POST' })
}
