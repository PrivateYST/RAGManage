/** 操作日志表格的列定义与展示转换，避免页面入口承载列表细节。 */

import type { AuditLogItem } from '@/api/audit'
import type { AppTableColumn } from '@/components'

/** 将服务端时间转换为用户本地的 24 小时制展示。 */
export function formatAuditTableTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

/** 生成表格中的安全摘要预览；完整 JSON 仅在详情弹窗展示。 */
export function auditSummaryText(item: AuditLogItem): string {
  const entries = Object.entries(item.change_summary)
  if (!entries.length) return '没有附加变更摘要'
  const text = entries
    .slice(0, 3)
    .map(
      ([key, value]) =>
        `${key}: ${typeof value === 'object' ? JSON.stringify(value) : String(value)}`,
    )
    .join(' · ')
  return text.length > 120 ? `${text.slice(0, 117)}…` : text
}

/** AppTable 列只声明稳定的列契约，具体单元格由模板渲染。 */
export const auditColumns: AppTableColumn<AuditLogItem>[] = [
  { key: 'time', title: '时间', cellClass: 'whitespace-nowrap px-[18px] py-[14px]' },
  { key: 'actor', title: '操作人', cellClass: 'px-[18px] py-[14px]' },
  { key: 'action', title: '操作', cellClass: 'px-[18px] py-[14px]' },
  { key: 'target', title: '目标', cellClass: 'px-[18px] py-[14px]' },
  { key: 'summary', title: '变更摘要', cellClass: 'px-[18px] py-[14px]' },
  { key: 'scope', title: '范围', cellClass: 'px-[18px] py-[14px]' },
  { key: 'details', title: '操作', cellClass: 'px-[18px] py-[14px]' },
]

export type { AuditTableEmits, AuditTableProps } from './type'
