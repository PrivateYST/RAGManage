/** API Key 汇总表的属性契约。 */
import type { CompanyApiKey } from '@/api/apiKeys'

export interface ApiKeyTableProps {
  items: CompanyApiKey[]
  loading: boolean
  busyId: string
}
