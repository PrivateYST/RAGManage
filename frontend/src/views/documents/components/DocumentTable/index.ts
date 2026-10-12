/** 文档表格逻辑：封装解析状态、文件大小和日期的展示格式。 */
const PARSE_LABELS: Record<string, string> = {
  complete: '解析完成',
  partial: '部分完成',
  processing: '解析中',
  queued: '等待处理',
  failed: '解析失败',
  unsupported: '不支持',
}

/** 将解析状态映射到可读标签，未知状态保留后端原值。 */
export function parseLabel(status: string | null): string {
  return status ? (PARSE_LABELS[status] ?? status) : '暂无版本'
}

/** 按状态语义选择 badge 颜色，错误色仅用于失败与不支持状态。 */
export function parseStatusClass(status: string | null): string {
  if (status === 'complete') return 'bg-status-up-soft text-status-up'
  if (status === 'failed' || status === 'unsupported') return 'bg-destructive/10 text-destructive'
  return 'bg-status-warning-soft text-status-warning'
}

/** 将字节数转换为列表中紧凑可读的文件大小。 */
export function formatSize(size: number | null): string {
  if (!size) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

/** 将时间戳格式化为本地时间；缺失值显示占位符。 */
export function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}
