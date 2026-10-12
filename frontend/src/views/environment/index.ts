import type { EnvironmentHealth } from './type'

/** 环境检查页面逻辑：管理依赖健康查询、刷新取消、超时和即时错误提醒。 */
import { onMounted, onUnmounted, shallowRef } from 'vue'
import { fetchHealth } from '@/api/health'
import { useAppToast } from '@/composables/useToast'

/** 提供健康数据和可重复调用的检查动作，页面卸载时释放正在运行的请求。 */
export function useEnvironmentPage() {
  const health = shallowRef<EnvironmentHealth | null>(null)
  const loading = shallowRef(false)
  const errorMessage = shallowRef<string | null>(null)
  const toast = useAppToast()
  let controller: AbortController | undefined

  /** 新检查会取消前一个请求，且只有最新请求可以收尾当前加载状态。 */
  async function refresh(): Promise<void> {
    controller?.abort()
    const requestController = new AbortController()
    controller = requestController
    loading.value = true
    health.value = null
    errorMessage.value = null
    const timeout = setTimeout(() => requestController.abort(), 10000)
    try {
      health.value = await fetchHealth(requestController.signal)
    } catch {
      // 卸载、超时或被后续刷新取消时不弹出网络失败提示，避免把取消误报为服务异常。
      if (!requestController.signal.aborted) {
        errorMessage.value = '服务状态暂时无法读取，请确认后端服务已启动后重试。'
        toast.error('服务状态检查失败', '请检查后端服务是否启动后重试。')
      }
    } finally {
      clearTimeout(timeout)
      if (controller === requestController) loading.value = false
    }
  }

  onMounted(() => void refresh())
  onUnmounted(() => controller?.abort())

  return { errorMessage, health, loading, refresh }
}
