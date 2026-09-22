/** 一次性明文 Key 的复制行为，不在浏览器持久化凭据。 */
import type { ApiKeyRevealDialogProps } from './type'
import { shallowRef } from 'vue'
import { useAppToast } from '@/composables/useToast'

/** 管理一次性明文的剪贴板写入、并发禁用和失败反馈。 */
export function useApiKeyRevealDialog(
  props: ApiKeyRevealDialogProps,
  emit: (event: 'copied') => void,
) {
  const toast = useAppToast()
  const copying = shallowRef(false)

  /** 尝试写入系统剪贴板；权限失败时保留明文并提示手动复制。 */
  async function copy(): Promise<void> {
    if (!props.apiKey || copying.value) return
    copying.value = true
    try {
      await navigator.clipboard.writeText(props.apiKey.raw_key)
      emit('copied')
    } catch {
      toast.error('复制失败', '请手动选择并复制 API Key。')
    } finally {
      copying.value = false
    }
  }

  return { copying, copy }
}
