import type { RuntimeStatusMetrics } from './type'

/** 运行状态页的数据协调：集中管理加载、重试和卸载时的请求取消。 */
import { onMounted, onUnmounted, shallowRef } from 'vue'
import { fetchRuntimeMetrics } from '@/api/health'

/** 提供页面展示状态及显式刷新动作，避免异步流程散落在模板组件。 */
export function useRuntimeStatusPage() {
  const metrics = shallowRef<RuntimeStatusMetrics | null>(null)
  const loading = shallowRef(true)
  const errorMessage = shallowRef<string | null>(null)
  let controller: AbortController | undefined

  /** 取消过期请求后再发起新请求，避免较早响应覆盖最新刷新结果。 */
  async function refresh(): Promise<void> {
    controller?.abort()
    const requestController = new AbortController()
    controller = requestController
    loading.value = true
    errorMessage.value = null
    try {
      metrics.value = await fetchRuntimeMetrics(requestController.signal)
    } catch (cause) {
      if (!requestController.signal.aborted) {
        errorMessage.value = cause instanceof Error ? cause.message : '平台运行指标加载失败'
      }
    } finally {
      if (controller === requestController) loading.value = false
    }
  }

  onMounted(() => void refresh())
  onUnmounted(() => controller?.abort())

  return { errorMessage, loading, metrics, refresh }
}

/** 将字节数量格式化为便于后台运维读取的 IEC 单位。 */
export function formatBytes(value?: number): string {
  if (value === undefined) return '不可用'
  if (value < 1024) return `${value} B`
  const units = ['KiB', 'MiB', 'GiB', 'TiB']
  let amount = value
  let unit = 'B'
  for (const next of units) {
    amount /= 1024
    unit = next
    if (amount < 1024) break
  }
  return `${amount.toFixed(1)} ${unit}`
}
