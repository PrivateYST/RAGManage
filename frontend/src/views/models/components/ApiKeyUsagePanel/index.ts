/** API Key 用量面板的来源标签。 */
import type { ApiKeyUsageRow } from '@/api/apiKeys'

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
