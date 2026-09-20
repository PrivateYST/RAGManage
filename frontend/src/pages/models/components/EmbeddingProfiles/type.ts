import type { EmbeddingProfile, ModelEndpoint } from '../../../../api/models'

export interface EmbeddingProfilesProps {
  items: EmbeddingProfile[]
  endpoints: ModelEndpoint[]
}
