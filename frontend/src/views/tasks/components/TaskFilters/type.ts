import type { TaskFilterValue } from '../../type'
/** 任务筛选栏的受控数据契约；筛选状态由页面持有，避免子视图私自触发请求。 */
import type { KnowledgeBaseRow } from '@/api/admin'

/** 筛选控件选项及当前结果数量。 */
export interface TaskFiltersProps {
  knowledgeBases: KnowledgeBaseRow[]
  knowledgeBaseId: TaskFilterValue
  stateFilter: TaskFilterValue
  visibleTaskCount: number
}

/** 两个双向筛选事件向父页面报告新值。 */
export interface TaskFiltersEmits {
  'update:knowledgeBaseId': [value: TaskFilterValue]
  'update:stateFilter': [value: TaskFilterValue]
}
