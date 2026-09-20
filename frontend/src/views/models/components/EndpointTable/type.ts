import type { ModelEndpoint } from '@/api/models'

export interface EndpointTableProps {
  items: ModelEndpoint[]
  loading: boolean
  busyId: string
}
