export interface Health {
  status: 'ready' | 'not_ready'
  checks: Record<string, string>
}

export async function fetchHealth(signal: AbortSignal): Promise<Health> {
  const response = await fetch('/api/v1/health/ready', { signal })
  if (response.status !== 200 && response.status !== 503) {
    throw new Error('无法读取服务状态')
  }
  const body: unknown = await response.json()
  if (
    !body
    || typeof body !== 'object'
    || !('status' in body)
    || !['ready', 'not_ready'].includes(String(body.status))
    || !('checks' in body)
    || !body.checks
    || typeof body.checks !== 'object'
    || Array.isArray(body.checks)
    || !Object.values(body.checks).every(value => typeof value === 'string')
  ) {
    throw new Error('服务返回了无效的状态信息')
  }
  return body as Health
}
