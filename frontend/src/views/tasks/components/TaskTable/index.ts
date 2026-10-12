/** 任务表格的纯展示格式化和统一 AppTable 列定义。 */
import type { TaskRow } from '@/api/documents'
import type { AppTableColumn } from '@/components'

/** 每个任务列提供统一的表头与单元格间距，AppTable 负责实际渲染。 */
export const taskColumns: AppTableColumn<TaskRow>[] = [
  { key: 'task', title: '任务', cellClass: 'px-[18px] py-[14px]' },
  { key: 'knowledgeBase', title: '知识库', cellClass: 'px-[18px] py-[14px]' },
  { key: 'state', title: '状态', cellClass: 'px-[18px] py-[14px]' },
  { key: 'progress', title: '进度', cellClass: 'px-[18px] py-[14px]' },
  { key: 'attempt', title: '尝试次数', field: 'attempt', cellClass: 'px-[18px] py-[14px]' },
  { key: 'created', title: '创建时间', cellClass: 'px-[18px] py-[14px]' },
  { key: 'updated', title: '更新时间', cellClass: 'px-[18px] py-[14px]' },
  { key: 'actions', title: '操作', cellClass: 'px-[18px] py-[14px]' },
]

/** 映射服务端任务状态；新增的非标准状态仍能以原始值排查。 */
export function taskStateLabel(state: string): string {
  return (
    {
      queued: '排队中',
      running: '处理中',
      completed: '已完成',
      failed: '失败',
      cancelled: '已取消',
      interrupted: '已中断',
    }[state] ?? state
  )
}

/** 映射已知任务类型，保留未知类型标识以便排障。 */
export function taskTypeLabel(taskType: string): string {
  return (
    {
      document_parse: '文档解析',
      document_embed: '文档嵌入',
      index_build: '索引构建',
    }[taskType] ?? taskType
  )
}

/** 使用中文 24 小时时间格式呈现任务时间戳。 */
export function formatTaskDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

/** 无可计数项目时仅对已完成任务显示完成态，其余保持占位符。 */
export function taskProgress(task: TaskRow): string {
  if (!task.item_count) return task.state === 'completed' ? '已完成' : '—'
  return `${task.completed_items} / ${task.item_count}`
}

/** 任务状态颜色只表达实际状态分类，避免为未知状态推断成功或失败。 */
export function taskStatusClass(state: string): string {
  if (state === 'completed') return 'bg-status-up-soft text-status-up'
  if (['failed', 'cancelled', 'interrupted'].includes(state))
    return 'bg-destructive/10 text-destructive'
  if (state === 'running') return 'bg-primary/10 text-primary'
  return 'bg-status-warning-soft text-status-warning'
}

/** 任务图标底色复用对应的成功、失败和待处理状态语义。 */
export function taskIconClass(state: string): string {
  if (state === 'completed') return 'bg-status-up-soft text-status-up'
  if (state === 'failed') return 'bg-destructive/10 text-destructive'
  return 'bg-status-warning-soft text-status-warning'
}
