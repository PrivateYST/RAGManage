/**
 * 全局数据表格的类型契约。
 *
 * 列只描述表头和字段读取方式，单元格的复杂展示通过具名插槽覆盖，
 * 从而让组件同时适用于简单字段表格和带操作、状态的业务表格。
 */
export interface AppTableColumn<T> {
  key: string
  title: string
  field?: keyof T | string
  width?: string
  align?: 'left' | 'center' | 'right'
  headerClass?: string
  cellClass?: string
  format?: (value: unknown, row: T, index: number) => string | number
}

/** 分页状态；页码从 1 开始，和 Reka UI Pagination 的约定保持一致。 */
export interface AppTablePagination {
  page: number
  pageSize: number
  total: number
}
