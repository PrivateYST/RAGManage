/** 构建详情弹窗的只读展示逻辑，不执行构建状态变更。 */

import type { BuildDetailResponse } from '@/api/builds'

/** 将服务端时间格式化为本地 24 小时制，便于对齐任务记录。 */
export function formatBuildDetailDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

/** 长摘要仅显示前缀，完整配置仍由服务端保留。 */
export function shortBuildDetailHash(value: string): string {
  return value.length > 16 ? value.slice(0, 16) : value
}

/** 将底层接入标识转换为管理员可读名称。 */
export function buildDetailProviderLabel(value: string): string {
  return value === 'open_webui' ? 'Open WebUI 网关' : value === 'ollama' ? 'Ollama 直连' : value
}

/** 仅翻译已知处理状态，未知状态保留原值便于诊断。 */
export function buildDocumentStateLabel(value: string): string {
  return value === 'completed' ? '构建完成' : value === 'failed' ? '失败' : value
}

/** 优先展示明确错误信息，其次展示错误码，缺失错误时返回占位符。 */
export function buildDocumentErrorMessage(error: Record<string, unknown> | null): string {
  if (!error) return '—'
  return typeof error.message === 'string'
    ? error.message
    : typeof error.code === 'string'
      ? error.code
      : '处理失败'
}

/** 汇总清单中的切片和向量数；尚未加载详情时返回零。 */
export function buildDetailTotals(detail: BuildDetailResponse | null): {
  chunks: number
  embedded: number
} {
  if (!detail) return { chunks: 0, embedded: 0 }
  return detail.items.reduce(
    (totals, item) => ({
      chunks: totals.chunks + item.chunk_count,
      embedded: totals.embedded + item.embedded_count,
    }),
    { chunks: 0, embedded: 0 },
  )
}
