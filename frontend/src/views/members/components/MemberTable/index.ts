import type { SpaceRoleCode } from '@/api/members'
import { SPACE_ROLE_LABELS } from '@/views/members/enum'

export const spaceRoleOptions = Object.entries(SPACE_ROLE_LABELS) as [SpaceRoleCode, string][]

export function formatJoinDate(value?: string): string {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '—'
}
