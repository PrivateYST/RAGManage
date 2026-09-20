import { apiRequest } from './client'

export type BuildState = 'queued' | 'running' | 'validating' | 'ready' | 'failed' | 'cancelled'

export interface BuildRow {
  id: string
  tenant_id: string
  knowledge_base_id: string
  knowledge_base_name: string
  input_epoch: number
  state: BuildState
  error: Record<string, unknown> | null
  task_id: string
  model_name: string
  model_revision: string
  dimension: number
  embedding_profile_id: string
  embedding_definition_hash: string
  provider: string
  base_url: string
  release_id: string | null
  is_active_release: boolean
  document_count: number
  completed_documents: number
  chunk_count: number
  embedded_count: number
  created_at: string
  updated_at: string
}

export interface BuildDetailRecord {
  id: string
  tenant_id: string
  knowledge_base_id: string
  input_epoch: number
  state: BuildState
  error: Record<string, unknown> | null
  task_id: string
  embedding_profile_id: string
  model_name: string
  model_revision: string
  dimension: number
  embedding_definition_hash: string
  provider: string
  base_url: string
  release_id: string | null
  is_active_release: boolean
  created_at: string
  updated_at: string
}

export interface BuildDetailItem {
  document_id: string
  title: string
  document_version_id: string
  version_no: number
  artifact_id: string
  state: string
  chunk_count: number
  embedded_count: number
  error: Record<string, unknown> | null
  updated_at: string
}

export interface BuildDetailResponse {
  build: BuildDetailRecord
  items: BuildDetailItem[]
}

export interface ReleaseRow {
  id: string
  build_id: string
  manifest_hash: string
  state: 'ready' | 'retired' | 'invalidated'
  created_at: string
  embedding_profile_id: string
  model_name: string
  model_revision: string
  dimension: number
  embedding_definition_hash: string
  provider: string
  base_url: string
  document_count: number
  is_active: boolean
  rollback_available: boolean
}

export interface ReleaseConfigSnapshot {
  id?: string
  build_id?: string
  knowledge_base_id?: string
  knowledge_base_name?: string
  input_epoch?: number
  manifest_hash: string
  state?: string
  created_at?: string
  embedding_profile_id: string
  embedding_definition_hash: string
  ingestion_profile_id?: string
  ingestion_definition_hash?: string
  model_name: string
  model_revision: string
  dimension: number
  provider: string
  base_url: string
}

export type ReleaseChange = 'added' | 'updated' | 'removed' | 'unchanged'

export interface ReleaseDiffItem {
  document_id: string
  title: string
  change: ReleaseChange
  from_version: number | null
  to_version: number | null
}

export interface ReleasePreview {
  build: ReleaseConfigSnapshot
  current_release: ReleaseConfigSnapshot | null
  expected_active_release_id: string | null
  validation: {
    ready: boolean
    errors: Array<{ code: string, message: string, document_id?: string, title?: string }>
  }
  diff: {
    counts: Record<ReleaseChange, number>
    items: ReleaseDiffItem[]
  }
}

export interface PublishResult {
  id: string
  build_id: string
  manifest_hash: string
  state: string
  created_at: string
  reused: boolean
}

export interface RollbackResult {
  id: string
  build_id: string
  manifest_hash: string
  state: string
  created_at: string
  previous_release_id: string
}

export interface BuildCreateResult {
  id: string
  task_id: string
  state: BuildState
  input_epoch: number
  knowledge_base_id: string
  document_count: number
  model_name: string
  model_revision: string
  dimension: number
  reused: boolean
  created_at: string
  updated_at: string
}

export function fetchBuilds(filters: { tenantId?: string, knowledgeBaseId?: string } = {}): Promise<{ items: BuildRow[] }> {
  const query = new URLSearchParams()
  if (filters.tenantId)
    query.set('tenant_id', filters.tenantId)
  if (filters.knowledgeBaseId)
    query.set('knowledge_base_id', filters.knowledgeBaseId)
  const suffix = query.size ? `?${query.toString()}` : ''
  return apiRequest(`/api/v1/builds${suffix}`)
}

export function createBuild(knowledgeBaseId: string): Promise<BuildCreateResult> {
  return apiRequest(`/api/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/builds`, {
    method: 'POST',
  })
}

export function fetchBuildDetail(buildId: string): Promise<BuildDetailResponse> {
  return apiRequest(`/api/v1/builds/${encodeURIComponent(buildId)}`)
}

export function fetchReleasePreview(buildId: string): Promise<ReleasePreview> {
  return apiRequest(`/api/v1/builds/${encodeURIComponent(buildId)}/release-preview`)
}

export function publishBuild(
  buildId: string,
  expectedActiveReleaseId: string | null,
): Promise<PublishResult> {
  return apiRequest(`/api/v1/builds/${encodeURIComponent(buildId)}/publish`, {
    method: 'POST',
    body: JSON.stringify({ expected_active_release_id: expectedActiveReleaseId }),
  })
}

export function fetchReleases(
  knowledgeBaseId: string,
): Promise<{ active_release_id: string | null, items: ReleaseRow[] }> {
  return apiRequest(
    `/api/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseId)}/releases`,
  )
}

export function rollbackRelease(
  releaseId: string,
  expectedActiveReleaseId: string,
): Promise<RollbackResult> {
  return apiRequest(`/api/v1/releases/${encodeURIComponent(releaseId)}/rollback`, {
    method: 'POST',
    body: JSON.stringify({ expected_active_release_id: expectedActiveReleaseId }),
  })
}
