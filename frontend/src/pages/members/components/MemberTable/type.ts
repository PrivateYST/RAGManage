import type { SpaceMember, SpaceRoleCode } from '../../../../api/members'

export interface MemberTableProps {
  items: SpaceMember[]
  loading: boolean
  busyId: string
}

export interface MemberTableEmits {
  (event: 'changeRole', member: SpaceMember, roleCode: SpaceRoleCode): void
  (event: 'toggleStatus', member: SpaceMember): void
}
