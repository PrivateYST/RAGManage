import type { EndpointInput, ModelEndpoint } from '@/api/models'

export interface EndpointDialogState {
  open: boolean
  endpoint: ModelEndpoint | null
}

export interface EndpointSubmitPayload extends EndpointInput {
  id?: string
}

/** 模型配置页的三个互斥工作区。 */
export type ModelPageView = 'endpoints' | 'profiles' | 'api-keys'
