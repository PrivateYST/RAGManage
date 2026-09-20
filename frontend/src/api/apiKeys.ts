/** 公司 API Key 管理接口：仅超级管理员可调用，明文只在创建响应中出现一次。 */
import { apiRequest } from './client'

export type ApiKeyStatus = 'active' | 'revoked' | 'expired'

/** 管理列表中的公司 API Key，不包含不可再次读取的明文凭据。 */
export interface CompanyApiKey {
  id: string
  tenant_id: string
  tenant_name?: string
  name: string
  key_prefix: string
  token_limit: number
  token_used: number
  token_reserved: number
  token_remaining: number
  prompt_tokens: number
  completion_tokens: number
  status: ApiKeyStatus
  expires_at: string | null
  last_used_at: string | null
  created_at: string
  revoked_at: string | null
}

/** 单个模型在一次问答中的 Token 用量。 */
export interface ApiKeyModelUsage {
  model: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  usage_source: 'gateway' | 'estimate' | 'unavailable'
}

/** 创建成功响应；raw_key 仅在本次响应中返回。 */
export interface CreatedApiKey extends CompanyApiKey {
  raw_key: string
}

/** 最近一次问答的总用量与嵌入、生成分项。 */
export interface ApiKeyUsageRow {
  request_id: string
  model_name: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  usage_source: 'gateway' | 'estimate' | 'unavailable'
  model_usage: {
    embedding?: ApiKeyModelUsage
    generation?: ApiKeyModelUsage
  }
  status: 'completed' | 'failed' | 'cancelled'
  created_at: string
  completed_at: string
}

/** API Key 从全部历史流水聚合出的累计用量。 */
export interface ApiKeyUsageSummary {
  request_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

/** 用量接口同时返回全量汇总和限定数量的最近流水。 */
export interface ApiKeyUsageResponse {
  summary: ApiKeyUsageSummary
  recent_limit: number
  items: ApiKeyUsageRow[]
}

/** 获取全部公司 API Key 的额度和累计状态。 */
export function fetchApiKeys(): Promise<{ items: CompanyApiKey[] }> {
  return apiRequest('/api/v1/api-keys')
}

/** 创建一次性展示的公司 API Key。 */
export function createApiKey(payload: {
  tenant_id: number
  name: string
  token_limit: number
  expires_at: string | null
}): Promise<CreatedApiKey> {
  return apiRequest('/api/v1/api-keys', { method: 'POST', body: JSON.stringify(payload) })
}

/** 立即撤销指定 API Key，撤销后不能恢复调用。 */
export function revokeApiKey(id: string): Promise<Pick<CompanyApiKey, 'id' | 'name' | 'status'>> {
  return apiRequest(`/api/v1/api-keys/${encodeURIComponent(id)}/revoke`, { method: 'POST' })
}

/** 获取指定 Key 的全量汇总及最近用量流水。 */
export function fetchApiKeyUsage(id: string): Promise<ApiKeyUsageResponse> {
  return apiRequest(`/api/v1/api-keys/${encodeURIComponent(id)}/usage`)
}
