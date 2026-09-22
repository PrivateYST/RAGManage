<!--
  全局数据表格：使用 TanStack Table 生成表头、行和单元格模型，
  通过 shadcn-vue 风格的 Table 原语渲染，并组合 Reka UI 分页。
-->
<script setup lang="ts" generic="T">
import type { ColumnDef } from '@tanstack/vue-table'
import type { AppTableColumn, AppTablePagination } from './type'
import { FlexRender, getCoreRowModel, useVueTable } from '@tanstack/vue-table'
import {
  PaginationEllipsis,
  PaginationList,
  PaginationListItem,
  PaginationNext,
  PaginationPrev,
  PaginationRoot,
} from 'reka-ui'
import { computed, shallowRef, watch } from 'vue'
import { ChevronLeft, ChevronRight } from '@/components/icons'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

interface Props {
  rows: T[]
  columns: AppTableColumn<T>[]
  loading?: boolean
  pagination?: AppTablePagination
  pageSizeOptions?: number[]
  clientPagination?: boolean
  rowKey?: keyof T | ((row: T, index: number) => string | number)
  emptyText?: string
  loadingText?: string
  tableClass?: string
}

defineOptions({ inheritAttrs: false })

const props = withDefaults(defineProps<Props>(), {
  loading: false,
  pagination: undefined,
  pageSizeOptions: () => [10, 20, 50],
  clientPagination: false,
  rowKey: undefined,
  emptyText: '暂无数据',
  loadingText: '正在加载…',
  tableClass: '',
})

const emit = defineEmits<{
  pageChange: [pagination: AppTablePagination]
  pageSizeChange: [pagination: AppTablePagination]
}>()
const internalPage = shallowRef(1)
const internalPageSize = shallowRef(props.pagination?.pageSize ?? props.pageSizeOptions[0] ?? 10)
const isClientPagination = computed(() => props.clientPagination || !props.pagination)
const total = computed(() => props.pagination?.total ?? props.rows.length)
const page = computed(() =>
  isClientPagination.value ? internalPage.value : (props.pagination?.page ?? 1),
)
const pageSize = computed(() =>
  isClientPagination.value
    ? internalPageSize.value
    : (props.pagination?.pageSize ?? internalPageSize.value),
)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const displayedRows = computed(() => {
  if (!isClientPagination.value) return props.rows
  const start = (page.value - 1) * pageSize.value
  return props.rows.slice(start, start + pageSize.value)
})
const rangeStart = computed(() => (total.value ? (page.value - 1) * pageSize.value + 1 : 0))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, total.value))
watch(
  () => props.pagination,
  (value) => {
    if (!value) return
    internalPage.value = value.page
    internalPageSize.value = value.pageSize
  },
  { immediate: true },
)

function cellValue(column: AppTableColumn<T>, row: T, index: number): string | number {
  const value = column.field === undefined ? undefined : row[column.field as keyof T]
  return column.format
    ? column.format(value, row, index)
    : ((value as string | number | undefined) ?? '—')
}
function getRowKey(row: T, index: number): string | number {
  if (typeof props.rowKey === 'function') return props.rowKey(row, index)
  if (props.rowKey !== undefined) return String(row[props.rowKey])
  return index
}
const columnDefs = computed<ColumnDef<T>[]>(() =>
  props.columns.map((column) => ({
    id: column.key,
    accessorFn: (row) => (column.field === undefined ? undefined : row[column.field as keyof T]),
    header: () => column.title,
    cell: (context) => cellValue(column, context.row.original, context.row.index),
    meta: column,
  })),
)
const table = useVueTable({
  get data() {
    return displayedRows.value
  },
  get columns() {
    return columnDefs.value
  },
  getCoreRowModel: getCoreRowModel(),
  getRowId: (row, index) => String(getRowKey(row, index)),
})
function handlePageChange(nextPage: number): void {
  const normalizedPage = Math.min(Math.max(nextPage, 1), pageCount.value)
  if (isClientPagination.value) {
    internalPage.value = normalizedPage
    return
  }
  emit('pageChange', { page: normalizedPage, pageSize: pageSize.value, total: total.value })
}
function handlePageSizeChange(event: Event): void {
  const nextPageSize = Number((event.target as HTMLSelectElement).value)
  if (!Number.isFinite(nextPageSize) || nextPageSize <= 0) return
  const nextPagination = { page: 1, pageSize: nextPageSize, total: total.value }
  if (isClientPagination.value) {
    internalPage.value = 1
    internalPageSize.value = nextPageSize
    return
  }
  emit('pageSizeChange', nextPagination)
}
</script>

<template>
  <section v-bind="$attrs" class="app-table" :class="{ 'app-table--loading': loading }">
    <div class="app-table__scroll">
      <Table :class="tableClass">
        <!-- 列组和 data-label 同时提供桌面列宽与窄屏可读性，避免业务表格各自重复对齐逻辑。 -->
        <colgroup>
          <col v-for="column in columns" :key="column.key" />
        </colgroup>
        <TableHeader>
          <TableRow v-for="headerGroup in table.getHeaderGroups()" :key="headerGroup.id">
            <TableHead
              v-for="header in headerGroup.headers"
              :key="header.id"
              :class="(header.column.columnDef.meta as AppTableColumn<T> | undefined)?.headerClass"
              :style="{
                textAlign: (header.column.columnDef.meta as AppTableColumn<T> | undefined)?.align,
              }"
            >
              <template v-if="!header.isPlaceholder">
                <slot :name="`header-${header.column.id}`" :column="header.column.columnDef.meta">
                  <FlexRender
                    :render="header.column.columnDef.header"
                    :props="header.getContext()"
                  />
                </slot>
              </template>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody v-if="loading">
          <TableRow
            ><TableCell class="app-table__state" :colspan="Math.max(columns.length, 1)">{{
              loadingText
            }}</TableCell></TableRow
          >
        </TableBody>
        <TableBody v-else-if="table.getRowModel().rows.length">
          <TableRow v-for="row in table.getRowModel().rows" :key="row.id">
            <TableCell
              v-for="cell in row.getVisibleCells()"
              :key="cell.id"
              :data-label="(cell.column.columnDef.meta as AppTableColumn<T>).title"
              :class="(cell.column.columnDef.meta as AppTableColumn<T>).cellClass"
              :style="{ textAlign: (cell.column.columnDef.meta as AppTableColumn<T>).align }"
            >
              <slot
                :name="`cell-${cell.column.id}`"
                :row="row.original"
                :column="cell.column.columnDef.meta"
                :index="row.index"
              >
                <FlexRender :render="cell.column.columnDef.cell" :props="cell.getContext()" />
              </slot>
            </TableCell>
          </TableRow>
        </TableBody>
        <TableBody v-else>
          <TableRow
            ><TableCell class="app-table__state" :colspan="Math.max(columns.length, 1)"
              ><slot name="empty">{{ emptyText }}</slot></TableCell
            ></TableRow
          >
        </TableBody>
      </Table>
    </div>
    <footer v-if="total > 0 || pagination" class="app-table__footer">
      <span class="app-table__summary"
        >显示 {{ rangeStart }}-{{ rangeEnd }}，共 {{ total }} 条</span
      >
      <div class="app-table__controls">
        <label class="app-table__page-size"
          ><span>每页</span
          ><select :value="pageSize" aria-label="每页条数" @change="handlePageSizeChange">
            <option v-for="size in pageSizeOptions" :key="size" :value="size">{{ size }}</option>
          </select></label
        >
        <PaginationRoot
          :page="page"
          :items-per-page="pageSize"
          :total="total"
          :disabled="loading"
          :sibling-count="1"
          show-edges
          class="app-table__pagination"
          @update:page="handlePageChange"
        >
          <PaginationPrev class="app-table__page-button" aria-label="上一页"
            ><ChevronLeft :size="14" aria-hidden="true"
          /></PaginationPrev>
          <PaginationList class="app-table__page-list"
            ><template #default="{ items }"
              ><template
                v-for="(item, itemIndex) in items"
                :key="`${item.type}-${item.type === 'page' ? item.value : itemIndex}`"
              >
                <PaginationListItem
                  v-if="item.type === 'page'"
                  :value="item.value"
                  class="app-table__page-button"
                  >{{ item.value }}</PaginationListItem
                >
                <PaginationEllipsis
                  v-else
                  class="app-table__ellipsis"
                  aria-hidden="true"
                /> </template></template
          ></PaginationList>
          <PaginationNext class="app-table__page-button" aria-label="下一页"
            ><ChevronRight :size="14" aria-hidden="true"
          /></PaginationNext>
        </PaginationRoot>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.app-table {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--card);
}
.app-table__scroll {
  overflow-x: auto;
}
.app-table__scroll :deep(table) {
  min-width: 640px;
}
.app-table__state {
  height: 132px;
  color: var(--muted);
  text-align: center !important;
}
.app-table__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 56px;
  padding: 9px 14px;
  border-top: 1px solid var(--border);
  color: var(--muted);
  font-size: 11px;
}
.app-table__controls,
.app-table__page-size,
.app-table__pagination,
.app-table__page-list {
  display: flex;
  align-items: center;
  gap: 6px;
}
.app-table__controls {
  flex-wrap: wrap;
  justify-content: flex-end;
}
.app-table__page-size select {
  height: var(--table-control-height);
  padding: 0 8px;
  border: 1px solid var(--input);
  border-radius: 6px;
  color: var(--foreground);
  background: var(--background);
  font-size: 11px;
  outline: none;
}
.app-table__page-button {
  display: inline-flex;
  min-width: 30px;
  height: var(--table-control-height);
  align-items: center;
  justify-content: center;
  padding: 0 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--foreground);
  background: var(--background);
  font-size: 11px;
}
.app-table__page-button[data-selected='true'] {
  border-color: var(--primary);
  color: var(--primary-foreground);
  background: var(--primary);
}
.app-table__page-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
.app-table__ellipsis {
  min-width: 22px;
  text-align: center;
}
@media (max-width: 640px) {
  .app-table__footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .app-table__controls {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
