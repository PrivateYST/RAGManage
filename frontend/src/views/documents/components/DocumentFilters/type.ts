/** 文档筛选组件契约：筛选值由页面持有，子组件通过更新事件保持受控。 */
export interface DocumentFiltersProps {
  query: string
  status: string
  count: number
}

/** 筛选值更新事件由父页面同步回筛选状态。 */
export interface DocumentFiltersEmits {
  'update:query': [value: string]
  'update:status': [value: string]
}
