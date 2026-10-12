/** 服务状态展示的文字映射集中管理，让 API 状态码与中文界面保持对应。 */

/** 将健康检查返回的依赖名称转换为可读名称，未登记项保留原始标识。 */
export function getEnvironmentCheckLabel(name: string): string {
  const labels: Record<string, string> = {
    database: 'PostgreSQL / pgvector',
    redis: 'Redis',
    storage: '文件存储',
  }
  return labels[name] ?? name
}

/** 将服务端状态码转换为界面标签，未知状态明确显示待检查。 */
export function getEnvironmentStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    ok: '正常',
    unavailable: '无法连接',
    unconfigured: '待配置',
    vector_unavailable: '扩展未就绪',
  }
  return labels[status] ?? '待检查'
}
