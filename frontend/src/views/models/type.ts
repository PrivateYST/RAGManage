import type { EndpointInput, ModelEndpoint } from '@/api/models'

export interface EndpointDialogState {
  open: boolean
  endpoint: ModelEndpoint | null
}

export interface EndpointSubmitPayload extends EndpointInput {
  id?: string
}

export type ModelPageView = 'endpoints' | 'profiles'
