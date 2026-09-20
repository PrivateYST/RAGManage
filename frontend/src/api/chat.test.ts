import { describe, expect, it } from 'vitest'
import { consumeSseChunk } from './chat'

describe('sse parser', () => {
  it('reassembles arbitrary network fragments and multiple events', () => {
    const chunks = [
      'eve',
      'nt: token\nda',
      'ta: {"text":"你"}\n\nevent: token\ndata: {"te',
      'xt":"好"}\n\nevent: done\ndata: {"run":{"state":"completed"}}\n',
      '\n',
    ]
    let buffer = ''
    const events = []
    for (const chunk of chunks) {
      const parsed = consumeSseChunk(buffer, chunk)
      buffer = parsed.rest
      events.push(...parsed.events)
    }

    expect(buffer).toBe('')
    expect(events).toEqual([
      { event: 'token', data: { text: '你' } },
      { event: 'token', data: { text: '好' } },
      { event: 'done', data: { run: { state: 'completed' } } },
    ])
  })
})
