/** API Key 额度调整弹窗的属性和事件契约。 */
import type { ApiKeyQuotaAdjustment, CompanyApiKey } from '@/api/apiKeys'

export interface ApiKeyQuotaDialogProps {
  open: boolean
  apiKey: CompanyApiKey | null
  busy: boolean
}

export interface ApiKeyQuotaDialogEmits {
  close: []
  submit: [adjustment: ApiKeyQuotaAdjustment]
}
