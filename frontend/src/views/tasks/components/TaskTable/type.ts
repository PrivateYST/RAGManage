/** 任务表格接收经过页面筛选的记录，只通过事件请求父页面执行任务操作。 */
import type { TaskRow } from '@/api/documents'

/** 表格行数据、知识库名称映射及当前异步操作目标。 */
export interface TaskTableProps {
  rows: TaskRow[]
  knowledgeBaseNames: Map<string, string>
  busyTaskId: string | null
}

/** 任务重试和取消交给页面逻辑执行，以统一 API、Toast 和刷新时序。 */
export interface TaskTableEmits {
  retry: [task: TaskRow]
  cancel: [task: TaskRow]
}
