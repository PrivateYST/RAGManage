import type { ModelEndpointType } from '../../../../api/models'
import type { EndpointSubmitPayload } from '../../type'
import type { EndpointFormDialogProps } from './type'
import { reactive, shallowRef, watch } from 'vue'

const MODEL_SEPARATOR_PATTERN = /[\n,]/

export function useEndpointForm(props: EndpointFormDialogProps, emit: (event: 'submit', payload: EndpointSubmitPayload) => void) {
  const error = shallowRef('')
  const form = reactive({
    name: '',
    provider: 'open_webui',
    endpointType: 'generation' as ModelEndpointType,
    baseUrl: '',
    modelsText: '',
  })

  watch(
    () => [props.open, props.endpoint] as const,
    () => {
      if (!props.open)
        return
      error.value = ''
      form.name = props.endpoint?.name ?? ''
      form.provider = props.endpoint?.provider ?? 'open_webui'
      form.endpointType = props.endpoint?.endpoint_type ?? 'generation'
      form.baseUrl = props.endpoint?.base_url ?? ''
      form.modelsText = props.endpoint?.allowed_models.join('\n') ?? ''
    },
    { immediate: true },
  )

  function submit(): void {
    const allowedModels = [...new Set(form.modelsText.split(MODEL_SEPARATOR_PATTERN).map(item => item.trim()).filter(Boolean))]
    if (!allowedModels.length) {
      error.value = '请至少填写一个模型名称'
      return
    }
    emit('submit', {
      id: props.endpoint?.id,
      name: form.name.trim(),
      provider: form.provider,
      endpoint_type: form.endpointType,
      base_url: form.baseUrl.trim(),
      secret_ref: 'env:MODEL_GATEWAY_API_KEY',
      allowed_models: allowedModels,
    })
  }

  return { form, error, submit }
}
