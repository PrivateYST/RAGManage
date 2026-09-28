import type { AddMemberDialogEmits } from './type'
import type { SpaceRoleCode } from '@/api/members'
import { shallowRef } from 'vue'
import { SPACE_ROLE_LABELS } from '@/views/members/enum'

export const assignableSpaceRoles = Object.entries(SPACE_ROLE_LABELS) as [SpaceRoleCode, string][]

/**
 * 添加成员表单状态：提交回调由父级负责执行，done 是唯一允许结束 busy 状态的回调，
 * 避免异步请求尚未完成时用户重复添加同一账号。
 */
export function useAddMemberDialog(emit: AddMemberDialogEmits) {
  const login = shallowRef('')
  const roleCode = shallowRef<SpaceRoleCode>('space_member')
  const submitting = shallowRef(false)

  function close(): void {
    if (!submitting.value) emit('close')
  }

  function submit(): void {
    const normalizedLogin = login.value.trim()
    if (!normalizedLogin || submitting.value) return
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
