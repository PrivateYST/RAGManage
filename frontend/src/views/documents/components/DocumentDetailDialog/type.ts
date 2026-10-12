/** 文档详情弹窗契约：数据和异步操作均由页面持有，组件只负责呈现与事件转发。 */
import type { ChunkRow, DocumentDetail, DocumentVersionDiff } from '@/api/documents'

/** 提供详情、切片状态和格式化能力，保持弹窗可独立测试。 */
export interface DocumentDetailDialogProps {
  detail: DocumentDetail | null
  loading: boolean
  chunks: ChunkRow[]
  chunksLoading: boolean
  chunksError: string
  versionDiff: DocumentVersionDiff | null
  versionDiffLoading: boolean
  highlightedChunkId: string
  formatLocator: (locator: Record<string, number>) => string
  parseStatusLabel: (status: string) => string
  formatDate: (value: string) => string
}

/** 所有写操作继续由页面执行，以集中处理 API 和 Toast 反馈。 */
export interface DocumentDetailDialogEmits {
  close: []
  reparse: []
  rebuild: []
  download: [versionId: string]
  compare: []
}
