/** 模型网关密钥配置弹窗的加载、校验和保存逻辑。 */
import type { GatewayApiKeyDialogProps } from './type'
import { reactive, shallowRef, watch } from 'vue'
import { fetchModelGatewayKey, updateModelGatewayKey } from '@/api/models'
import { useAppToast } from '@/composables/useToast'

export function useGatewayApiKeyDialog(
  props: GatewayApiKeyDialogProps,
  emit: (event: 'close' | 'saved') => void,
) {
  const toast = useAppToast()
  const form = reactive({ apiKey: '' })
  const status = shallowRef<{
    configured: boolean
    source: 'environment' | 'system'
    masked: string
  } | null>(null)
  const loading = shallowRef(false)
  const submitting = shallowRef(false)
  const showKey = shallowRef(false)
  const error = shallowRef('')

  /** 打开弹窗时刷新脱敏状态，避免展示过期的来源信息。 */
  watch(
    () => props.open,
    async (open) => {
      if (!open) return
      form.apiKey = ''
      showKey.value = false
      error.value = ''
      loading.value = true
      try {
        status.value = await fetchModelGatewayKey()
      } catch (cause) {
        toast.error(cause instanceof Error ? cause.message : '网关密钥状态加载失败')
      } finally {
        loading.value = false
      }
    },
    { immediate: true },
  )

  /** 提交新密钥；服务端仅返回脱敏尾缀，保存成功后清空本地输入。 */
  async function submit(): Promise<void> {
    const apiKey = form.apiKey.trim()
    if (!apiKey) {
      error.value = '请输入 API Key'
      return
    }
    submitting.value = true
    error.value = ''
    try {
      status.value = await updateModelGatewayKey(apiKey)
      form.apiKey = ''
      emit('saved')
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '网关密钥保存失败')
    } finally {
      submitting.value = false
    }
  }

  return { form, status, loading, submitting, showKey, error, submit }
}
