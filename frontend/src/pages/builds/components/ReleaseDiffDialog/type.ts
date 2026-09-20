import type { ReleasePreview } from '../../../../api/builds'

export interface ReleaseDiffDialogProps {
  open: boolean
  loading: boolean
  publishing: boolean
  preview: ReleasePreview | null
}

export interface ReleaseDiffDialogActions {
  close: () => void
  publish: () => void
}
