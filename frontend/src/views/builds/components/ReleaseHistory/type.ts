import type { ReleaseRow } from '@/api/builds'

export interface ReleaseHistoryProps {
  releases: ReleaseRow[]
  loading: boolean
  selectedKnowledgeBaseName: string
}

export interface ReleaseHistoryEmits {
  view: [release: ReleaseRow]
  rollback: [release: ReleaseRow]
}
