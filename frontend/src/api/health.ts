export interface Health {
  status: 'ready' | 'not_ready'
  checks: Record<string, string>
}

/** 平台运行指标的聚合契约；接口不返回租户、正文或凭据等明细。 */
export interface RuntimeMetrics {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
  tasks: Record<string, number>
  models: { healthy: number; unhealthy: number; unknown: number }
  storage: {
    status: 'ok' | 'unavailable'
    used_bytes?: number
    free_bytes?: number
    total_bytes?: number
  }
}

export async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch('/api/v1/health/ready', { signal })
  if (response.status !== 200 && response.status !== 503) {
    throw new Error('无法读取服务状态')
  }
  const body: unknown = await response.json()
  if (
    !body ||
    typeof body !== 'object' ||
    !('status' in body) ||
    !['ready', 'not_ready'].includes(String(body.status)) ||
    !('checks' in body) ||
    !body.checks ||
    typeof body.checks !== 'object' ||
    Array.isArray(body.checks) ||
    !Object.values(body.checks).every((value) => typeof value === 'string')
  ) {
    throw new Error('服务返回了无效的状态信息')
  }
  return body as Health
}

/** 仅供平台运行状态页读取聚合指标，服务端负责平台管理员鉴权。 */
export async function fetchRuntimeMetrics(signal: AbortSignal): Promise<RuntimeMetrics> {
  const response = await fetch('/api/v1/health/metrics', { signal })
  if (!response.ok) throw new Error('无法读取平台运行指标')
  return (await response.json()) as RuntimeMetrics
}
