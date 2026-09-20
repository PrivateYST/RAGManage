import type { EmbeddingProfile, ModelEndpoint, RuntimeProfile } from '../../../../api/models'

export interface RuntimeProfilesProps {
  items: RuntimeProfile[]
  embeddingProfiles: EmbeddingProfile[]
  endpoints: ModelEndpoint[]
  busyId: string
}
