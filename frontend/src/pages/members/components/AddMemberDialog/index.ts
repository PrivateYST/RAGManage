import type { SpaceRoleCode } from '../../../../api/members'
import type { AddMemberDialogEmits } from './type'
import { shallowRef } from 'vue'
import { SPACE_ROLE_LABELS } from '../../enum'

export const assignableSpaceRoles = Object.entries(SPACE_ROLE_LABELS) as [SpaceRoleCode, string][]

export function useAddMemberDialog(emit: AddMemberDialogEmits) {
  const login = shallowRef('')
  const roleCode = shallowRef<SpaceRoleCode>('space_member')
  const submitting = shallowRef(false)

  function close(): void {
    if (!submitting.value)
      emit('close')
  }

  function submit(): void {
    const normalizedLogin = login.value.trim()
    if (!normalizedLogin || submitting.value)
      return
    submitting.value = true
    emit('submit', { login: normalizedLogin, roleCode: roleCode.value }, (success) => {
      submitting.value = false
      if (success) {
        login.value = ''
        roleCode.value = 'space_member'
        emit('close')
      }
    })
  }

  return { login, roleCode, submitting, close, submit }
}
