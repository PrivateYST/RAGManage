import type { ModelEndpoint } from '@/api/models'
import { reactive } from 'vue'

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
