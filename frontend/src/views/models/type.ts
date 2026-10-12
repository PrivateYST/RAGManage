import type { EndpointInput, ModelEndpoint } from '@/api/models'

export interface EndpointDialogState {
  open: boolean
  endpoint: ModelEndpoint | null
}

export interface EndpointSubmitPayload extends EndpointInput {
  id?: string
}

/** 模型配置页中按平台或医院权限显示的互斥工作区。 */
export type ModelPageView = 'endpoints' | 'profiles' | 'api-keys' | 'tenant-api-key'
