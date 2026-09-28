import { afterEach, expect, it, vi } from 'vitest'
import { fetchHealth, fetchRuntimeMetrics } from './health'

afterEach(() => vi.unstubAllGlobals())
it('preserves unavailable dependency details from a 503 response', async () => {
  const body = { status: 'not_ready', checks: { database: 'unavailable' } }
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 503 })),
  )
  expect(await fetchHealth(new AbortController().signal)).toEqual(body)
})
it('rejects an unrelated error response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 500 })))
  await expect(fetchHealth(new AbortController().signal)).rejects.toThrow()
})
it('rejects malformed service responses', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response('{"status":"ready","checks":null}')),
  )
  await expect(fetchHealth(new AbortController().signal)).rejects.toThrow()
})

it('reads aggregate runtime metrics without reshaping sensitive details', async () => {
  const body = {
    status: 'ok',
    database: 'ok',
    tasks: { queued: 1, running: 2, failed: 0 },
    models: { healthy: 1, unhealthy: 0, unknown: 0 },
    storage: { status: 'ok', used_bytes: 10, free_bytes: 20, total_bytes: 30 },
  }
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 })),
  )
  await expect(fetchRuntimeMetrics(new AbortController().signal)).resolves.toEqual(body)
})
