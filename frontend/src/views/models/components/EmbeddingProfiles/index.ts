import type { ModelEndpoint } from '@/api/models'
import { computed, reactive, watch } from 'vue'

export function useEmbeddingProfileForm(endpoints: () => ModelEndpoint[]) {
  const embeddingEndpoints = computed(() =>
    endpoints().filter((item) => item.endpoint_type === 'embedding' && item.status === 'active'),
  )
  const form = reactive({ endpointId: '', modelName: '', expectedDimension: 1024 })
  watch(
    embeddingEndpoints,
    (items) => {
      if (!items.some((item) => item.id === form.endpointId)) form.endpointId = items[0]?.id ?? ''
      const endpoint = items.find((item) => item.id === form.endpointId)
      if (!endpoint?.allowed_models.includes(form.modelName))
        form.modelName = endpoint?.allowed_models[0] ?? ''
    },
    { immediate: true },
  )
  watch(
    () => form.endpointId,
    (id) => {
      const endpoint = embeddingEndpoints.value.find((item) => item.id === id)
      form.modelName = endpoint?.allowed_models[0] ?? ''
      form.expectedDimension = endpoint?.observed_dimension ?? 1024
    },
  )
  return { form, embeddingEndpoints }
}
