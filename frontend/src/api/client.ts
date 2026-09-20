export async function apiRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...options.headers,
    },
  })
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string }
    throw new Error(body.detail ?? `请求失败（${response.status}）`)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
