import type { SpaceMember, SpaceRoleCode } from '@/api/members'
import type { AppTableColumn } from '@/components'
import { SPACE_ROLE_LABELS } from '@/views/members/enum'

export const spaceRoleOptions = Object.entries(SPACE_ROLE_LABELS) as [SpaceRoleCode, string][]

export function formatJoinDate(value?: string): string {
  return value ? new Date(value).toLocaleDateString('zh-CN') : '—'
}

/** 成员表格列契约集中维护，模板只负责渲染各列单元格。 */
export const memberColumns: AppTableColumn<SpaceMember>[] = [
  { key: 'member', title: '成员' },
  { key: 'role', title: '空间角色' },
  { key: 'grants', title: '知识库授权' },
  { key: 'status', title: '状态' },
  { key: 'joined', title: '加入日期' },
  { key: 'actions', title: '操作' },
]
