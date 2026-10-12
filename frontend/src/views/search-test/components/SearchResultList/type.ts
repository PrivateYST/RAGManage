import type { SearchTestResult } from '@/api/search'

/** 结果列表展示所需的检索结果与进行中状态。 */
export interface SearchResultListProps {
  result: SearchTestResult | null
  searching: boolean
}
