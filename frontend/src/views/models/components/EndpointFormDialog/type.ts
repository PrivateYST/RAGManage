import type { ModelEndpoint } from '@/api/models'

export interface EndpointFormDialogProps {
  open: boolean
  endpoint: ModelEndpoint | null
}
