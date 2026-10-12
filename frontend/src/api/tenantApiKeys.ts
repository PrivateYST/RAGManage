/** 医院已分配 API Key 的安全交接接口；请求只提交明文供服务端核验，不回传或保存明文。 */
import { apiRequest } from './client'

/** 医院最新一把已分配 Key 的脱敏配置状态。 */
export interface TenantApiKeyConfiguration {
  configured: boolean
  key_prefix: string | null
  status: 'active' | 'disabled' | 'revoked' | 'expired' | null
  configured_at: string | null
}

/** 查询当前医院最新一把 Key 的交接状态，不返回可调用的完整凭据。 */
export function fetchTenantApiKeyConfiguration(
  tenantId: string,
): Promise<TenantApiKeyConfiguration> {
  return apiRequest(`/api/v1/spaces/${encodeURIComponent(tenantId)}/api-key/configuration`)
}

/** 提交收到的医院 Key 供服务端按当前空间校验，并登记确认人及确认时间。 */
export function confirmTenantApiKeyConfiguration(
  tenantId: string,
  apiKey: string,
): Promise<TenantApiKeyConfiguration> {
  return apiRequest(`/api/v1/spaces/${encodeURIComponent(tenantId)}/api-key/configuration`, {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey }),
  })
}
