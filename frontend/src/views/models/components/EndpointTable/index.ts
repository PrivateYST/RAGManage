import type { ModelEndpoint } from '@/api/models'
import type { AppTableColumn } from '@/components'
import { reactive } from 'vue'
import { endpointTypeLabel } from '@/views/models/enum'

/** 端点表格列契约和展示转换集中维护，模板只负责渲染单元格。 */
export function endpointPurpose(endpoint: ModelEndpoint): string {
  return endpointTypeLabel[endpoint.endpoint_type]
}

export const endpointColumns: AppTableColumn<ModelEndpoint>[] = [
  { key: 'endpoint', title: '端点' },
  { key: 'purpose', title: '用途' },
  { key: 'models', title: '模型白名单' },
  { key: 'health', title: '健康状态' },
  { key: 'status', title: '状态' },
  { key: 'actions', title: '操作' },
]

export function useEndpointTable() {
  const selectedModels = reactive<Record<string, string>>({})

  function selectedModel(endpoint: ModelEndpoint): string {
    return selectedModels[endpoint.id] ?? endpoint.allowed_models[0] ?? ''
  }

  function setSelectedModel(endpointId: string, value: string): void {
    selectedModels[endpointId] = value
  }

  return { selectedModel, setSelectedModel }
}
