import type { AddSpaceMemberInput } from '../../type'

export interface AddMemberDialogProps {
  open: boolean
}

export interface AddMemberDialogEmits {
  (event: 'close'): void
  (event: 'submit', input: AddSpaceMemberInput, done: (success: boolean) => void): void
}
