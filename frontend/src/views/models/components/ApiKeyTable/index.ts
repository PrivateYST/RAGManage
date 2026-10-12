/** API Key 表格的状态和日期展示函数。 */
import type { ApiKeyStatus, CompanyApiKey } from '@/api/apiKeys'
import type { AppTableColumn } from '@/components'

export const apiKeyStatusLabel: Record<ApiKeyStatus, string> = {
  active: '启用',
  disabled: '停用',
  expired: '已过期',
  revoked: '已撤销',
}

/** 将可空服务端时间转换为本地显示文本。 */
export function formatApiKeyDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '尚未使用'
}

/** 医院 Key 表格列契约集中维护，明文读取仍只由父级管理器触发。 */
export const apiKeyColumns: AppTableColumn<CompanyApiKey>[] = [
  { key: 'client', title: '客户 / 名称' },
  { key: 'key', title: 'API Key' },
  { key: 'status', title: '状态' },
  { key: 'quota', title: '额度（总 / 已用 / 剩余）' },
  { key: 'usage', title: '输入 / 输出' },
  { key: 'lastUsed', title: '最后使用' },
  { key: 'actions', title: '操作' },
]
