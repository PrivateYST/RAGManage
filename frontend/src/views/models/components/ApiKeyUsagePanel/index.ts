/** API Key 用量面板的来源标签。 */
import type { ApiKeyUsageRow } from '@/api/apiKeys'
import type { AppTableColumn } from '@/components'

/** 提供用量来源的人类可读标签，汇总值直接信任后端全量聚合。 */
export function useApiKeyUsagePanel() {
  /** 区分网关真实值、回退估算和不可用状态。 */
  function sourceLabel(source: ApiKeyUsageRow['usage_source']): string {
    if (source === 'gateway') return '模型网关'
    if (source === 'estimate') return '回退估算'
    return '未返回'
  }

  return { sourceLabel }
}

/** 用量表格列契约集中维护，汇总和分项数据仍由服务端响应提供。 */
export const apiKeyUsageColumns: AppTableColumn<ApiKeyUsageRow>[] = [
  { key: 'time', title: '时间' },
  { key: 'models', title: '模型分项' },
  { key: 'prompt', title: '输入' },
  { key: 'completion', title: '输出' },
  { key: 'total', title: '合计' },
  { key: 'source', title: '来源' },
  { key: 'status', title: '状态' },
]

/** 将流水时间转换为本地展示文本。 */
export function formatApiKeyUsageDate(value: string): string {
  return new Date(value).toLocaleString()
}
