import { apiRequest } from './client'

export type ModelEndpointType = 'generation' | 'embedding' | 'reranker'
export type ModelEndpointStatus = 'active' | 'disabled'
export type HealthStatus = 'unknown' | 'healthy' | 'unhealthy'

export interface ModelEndpoint {
  id: string
  tenant_id: string | null
  name: string
  provider: string
  endpoint_type: ModelEndpointType
  base_url: string
  allowed_models: string[]
  health_status: HealthStatus
  status: ModelEndpointStatus
  last_checked_at: string | null
  last_latency_ms: number | null
  last_error: string | null
  observed_dimension: number | null
  secret_configured: boolean
  created_at: string
  updated_at: string
}

/** 当前模型网关 API Key 的脱敏状态；接口永不返回明文。 */
export interface ModelGatewayKeyStatus {
  configured: boolean
  source: 'environment' | 'system'
  masked: string
}

export interface IngestionProfile {
  id: string
  definition: {
    parser?: string
    chunking?: { strategy?: string; max_chars?: number; overlap_chars?: number }
    preserve_locator?: boolean
  }
  definition_hash: string
  created_at: string
  effect_scope: 'reparse_required'
}

export interface EmbeddingProfile {
  id: string
  model_endpoint_id: string
  endpoint_name: string
  endpoint_status: ModelEndpointStatus
  model_name: string
  model_revision: string
  dimension: number
  dtype: string
  instructions: { query?: string; document?: string }
  normalization: string
  definition_hash: string
  created_at: string
  effect_scope: 'rebuild_required'
}

export interface RuntimeProfile {
  id: string
  embedding_profile_id: string
  definition: {
    retrieval?: { mode?: string; top_k?: number; context_max_chars?: number }
    generation?: { endpoint_id?: number; model?: string; temperature?: number }
    answer_rules?: string
  }
  definition_hash: string
  created_at: string
  active: boolean
  effect_scope: 'immediate' | 'activate_required'
}

export interface ProfileCollection {
  knowledge_base_id: string
  ingestion_profiles: IngestionProfile[]
  embedding_profiles: EmbeddingProfile[]
  runtime_profiles: RuntimeProfile[]
}

export interface EndpointInput {
  name: string
  provider: string
  endpoint_type: ModelEndpointType
  base_url: string
  secret_ref: 'env:MODEL_GATEWAY_API_KEY'
  allowed_models: string[]
}

export interface HealthCheckResult {
  status: 'healthy' | 'unhealthy'
  model: string
  latency_ms?: number
  dimension?: number
  error?: string
}

export function fetchModelEndpoints(): Promise<{ items: ModelEndpoint[] }> {
  return apiRequest('/api/v1/model-endpoints')
}

/** 获取当前生效的模型网关密钥来源和脱敏尾缀。 */
export function fetchModelGatewayKey(): Promise<ModelGatewayKeyStatus> {
  return apiRequest('/api/v1/model-gateway-key')
}

/** 替换当前 API 进程使用的模型网关密钥，明文只在请求体中传输。 */
export function updateModelGatewayKey(apiKey: string): Promise<ModelGatewayKeyStatus> {
  return apiRequest('/api/v1/model-gateway-key', {
    method: 'PUT',
    body: JSON.stringify({ api_key: apiKey }),
  })
}

export function createModelEndpoint(payload: EndpointInput): Promise<ModelEndpoint> {
  return apiRequest('/api/v1/model-endpoints', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateModelEndpoint(
  id: string,
  payload: Partial<
    Pick<EndpointInput, 'name' | 'base_url' | 'allowed_models'> & { status: ModelEndpointStatus }
  >,
): Promise<ModelEndpoint> {
  return apiRequest(`/api/v1/model-endpoints/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function checkModelEndpoint(id: string, modelName: string): Promise<HealthCheckResult> {
  return apiRequest(`/api/v1/model-endpoints/${id}/health-check`, {
    method: 'POST',
    body: JSON.stringify({ model_name: modelName }),
  })
}

export function fetchProfiles(knowledgeBaseId: string): Promise<ProfileCollection> {
  return apiRequest(`/api/v1/profiles?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`)
}

export function createIngestionProfile(payload: {
  knowledge_base_id: number
  max_chars: number
  overlap_chars: number
  preserve_locator: boolean
}): Promise<IngestionProfile> {
  return apiRequest('/api/v1/ingestion-profiles', { method: 'POST', body: JSON.stringify(payload) })
}

export function createEmbeddingProfile(payload: {
  model_endpoint_id: number
  model_name: string
  expected_dimension: number | null
  normalization: string
  query_instruction: string
  document_instruction: string
}): Promise<EmbeddingProfile> {
  return apiRequest('/api/v1/embedding-profiles', { method: 'POST', body: JSON.stringify(payload) })
}

export function createRuntimeProfile(payload: {
  knowledge_base_id: number
  embedding_profile_id: number
  generation_endpoint_id: number
  generation_model: string
  top_k: number
  context_max_chars: number
  temperature: number
  answer_rules: string
}): Promise<RuntimeProfile> {
  return apiRequest('/api/v1/runtime-profiles', { method: 'POST', body: JSON.stringify(payload) })
}

export function activateRuntimeProfile(
  id: string,
): Promise<{ id: string; active: boolean; effect_scope: 'immediate' | 'rebuild_required' }> {
  return apiRequest(`/api/v1/runtime-profiles/${id}/activate`, { method: 'POST' })
}
