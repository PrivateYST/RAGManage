import { afterEach, expect, it, vi } from 'vitest'
import { fetchHealth } from './health'

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
