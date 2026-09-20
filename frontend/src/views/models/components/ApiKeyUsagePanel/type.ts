/** API Key 用量明细面板的属性契约。 */
import type { ApiKeyUsageRow, ApiKeyUsageSummary, CompanyApiKey } from '@/api/apiKeys'

/** 用量面板接收全量汇总和最近流水，两种口径必须分开呈现。 */
export interface ApiKeyUsagePanelProps {
  apiKey: CompanyApiKey | null
  items: ApiKeyUsageRow[]
  summary: ApiKeyUsageSummary | null
  recentLimit: number
  loading: boolean
}
