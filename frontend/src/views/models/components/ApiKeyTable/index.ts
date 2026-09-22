/** API Key 表格的状态和日期展示函数。 */
import type { ApiKeyStatus } from '@/api/apiKeys'

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
