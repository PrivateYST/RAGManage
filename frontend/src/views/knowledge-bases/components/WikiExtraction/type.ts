/** 生成面板只接收本库已发布文档，成功后通知容器刷新词条。 */
import type { WikiOptions } from '@/api/wiki'
export interface WikiExtractionProps {
  knowledgeBaseId: string
  options: WikiOptions
}
