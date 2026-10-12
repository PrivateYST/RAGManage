/** 知识库页面类型：定义创建表单和列表列配置使用的数据形状。 */
import type { KnowledgeBaseRow } from '@/api/admin'
import type { AppTableColumn } from '@/components'

/** 表单使用字符串空间 ID，提交时按 API 契约转换为数字。 */
export interface KnowledgeBaseForm {
  tenant_id: string
  name: string
  description: string
  purpose: string
}

/** 列表列由页面逻辑集中维护，模板只负责呈现单元格。 */
export type KnowledgeBaseColumn = AppTableColumn<KnowledgeBaseRow>
