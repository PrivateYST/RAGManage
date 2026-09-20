import { apiRequest } from './client'

export type SearchState = 'completed' | 'no_results' | 'index_not_ready' | 'sources_invalid'

export interface SearchEvidence {
  chunk_id: string
  document_id: string
  document_title: string
  document_version_id: string
  version_no: number
  content: string
  section_path: string[]
  locator: Record<string, number>
  similarity: number
  raw_rank: number
  vector_rank?: number
  lexical_rank?: number | null
  keyword_score?: number
  fused_score?: number
  route?: 'vector' | 'hybrid'
  rank: number
  context_included: boolean
  evidence_no: number | null
}

export interface SearchTestResult {
  trace_id: string
  state: SearchState
  message: string
  release: {
    id: string
    embedding_profile_id: string
    model_name: string
    model_revision: string
    dimension: number
    manifest_hash: string
  } | null
  source_stats: {
    total_documents: number
    valid_documents: number
    invalid_documents: number
    valid_chunks: number
    embedded_chunks: number
  } | null
  filters: Array<{ name: string, value: string, filtered_count: number }>
  timings: Record<string, number>
  context: string
  items: SearchEvidence[]
}

export function runSearchTest(payload: {
  knowledge_base_id: number
  query: string
  top_k: number
  context_max_chars: number
}): Promise<SearchTestResult> {
  return apiRequest('/api/v1/search-test', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
