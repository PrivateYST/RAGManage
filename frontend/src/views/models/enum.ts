import type { ModelEndpointType } from '@/api/models'

export const endpointTypeLabel: Record<ModelEndpointType, string> = {
  generation: '生成模型',
  embedding: '嵌入模型',
  reranker: '重排模型',
}

export const effectScopeLabel: Record<string, string> = {
  immediate: '立即生效',
  activate_required: '激活后生效',
  reparse_required: '重新解析后生效',
  rebuild_required: '需要重建并发布',
}
