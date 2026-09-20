import type { ModelEndpoint } from '@/api/models'
import { computed, reactive, watch } from 'vue'

export function useRuntimeProfileForm(endpoints: () => ModelEndpoint[]) {
  const generationEndpoints = computed(() =>
    endpoints().filter(item => item.endpoint_type === 'generation' && item.status === 'active'),
  )
  const form = reactive({
    embeddingProfileId: '',
    generationEndpointId: '',
    generationModel: '',
    topK: 10,
    contextMaxChars: 8000,
    temperature: 0.2,
    answerRules: '仅依据已发布资料回答；没有依据时明确拒答。',
  })
  watch(
    generationEndpoints,
    (items) => {
      if (!items.some(item => item.id === form.generationEndpointId))
        form.generationEndpointId = items[0]?.id ?? ''
    },
    { immediate: true },
  )
  watch(
    () => form.generationEndpointId,
    (id) => {
      const endpoint = generationEndpoints.value.find(item => item.id === id)
      form.generationModel = endpoint?.allowed_models[0] ?? ''
    },
    { immediate: true },
  )
  return { form, generationEndpoints }
}
