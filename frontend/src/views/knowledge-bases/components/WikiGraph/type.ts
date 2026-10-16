/** 图谱仅表达真实词条、别名及文档版本的来源关系，不推断语义事实。 */
import type { WikiEntry, WikiSource } from '@/api/wiki'

/** 图谱接收已通过现有知识库鉴权的词条，管理员可显示未发布状态。 */
export interface WikiGraphProps {
  entries: WikiEntry[]
  canManage: boolean
}

/** 可选节点保存业务引用，点击后可以追溯到对应版本和原文。 */
export interface GraphNode {
  id: string
  label: string
  kind: 'document' | 'entry' | 'alias'
  entries: WikiEntry[]
  sources: WikiSource[]
  x: number
  y: number
}

/** 有方向的来源或别名关系，布局坐标由节点字典推导。 */
export interface GraphEdge {
  id: string
  source: string
  target: string
  kind: 'source' | 'alias'
}

/** 布局后只输出存在端点的边，便于测试失效来源和过滤边界。 */
export interface WikiGraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
  truncated: boolean
}
