import type { BuildDetailResponse, ReleaseRow } from '@/api/builds'

export interface ReleaseDetailDialogProps {
  open: boolean
  loading: boolean
  error: string
  release: ReleaseRow | null
  detail: BuildDetailResponse | null
}

export interface ReleaseDetailDialogEmits {
  close: []
}
