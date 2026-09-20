/** API Key 创建弹窗的输入、属性和事件契约。 */
import type { TenantRow } from '@/api/admin'

export interface ApiKeyCreatePayload {
  tenant_id: number
  name: string
  token_limit: number
  expires_at: string | null
}

export interface ApiKeyCreateDialogProps {
  open: boolean
  tenants: TenantRow[]
  submitting: boolean
}
