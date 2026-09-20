import type { ReleaseRow } from '../../../../api/builds'

export interface ReleaseRollbackDialogProps {
  open: boolean
  rollingBack: boolean
  targetRelease: ReleaseRow | null
  currentRelease: ReleaseRow | null
}

export interface ReleaseRollbackDialogEmits {
  close: []
  confirm: []
}

export interface ReleaseRollbackDialogActions {
  close: () => void
  confirm: () => void
}
