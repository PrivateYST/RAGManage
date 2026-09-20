// @vitest-environment happy-dom

import type { ModelEndpoint } from '@/api/models'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import EndpointTable from './index.vue'

const endpoint: ModelEndpoint = {
  id: '2',
  tenant_id: null,
  name: '内部嵌入网关',
  provider: 'open_webui',
  endpoint_type: 'embedding',
  base_url: 'http://gateway.internal:8080',
  allowed_models: ['qwen3-embedding:0.6b'],
  health_status: 'healthy',
  status: 'active',
  last_checked_at: '2026-09-19T00:00:00Z',
  last_latency_ms: 18,
  last_error: null,
  observed_dimension: 1024,
  secret_configured: true,
  created_at: '2026-09-19T00:00:00Z',
  updated_at: '2026-09-19T00:00:00Z',
}

describe('endpoint table', () => {
  it('shows measured health and emits real endpoint operations', async () => {
    const wrapper = mount(EndpointTable, {
      props: { items: [endpoint], loading: false, busyId: '' },
    })

    expect(wrapper.text()).toContain('1024 维')
    expect(wrapper.text()).toContain('18 ms')
    const buttons = wrapper.findAll('button')
    await buttons[0]?.trigger('click')
    await buttons[1]?.trigger('click')

    expect(wrapper.emitted('check')?.[0]).toEqual([endpoint, 'qwen3-embedding:0.6b'])
    expect(wrapper.emitted('edit')?.[0]).toEqual([endpoint])
  })

  it('disables health checks for a stopped endpoint', () => {
    const wrapper = mount(EndpointTable, {
      props: { items: [{ ...endpoint, status: 'disabled' }], loading: false, busyId: '' },
    })

    expect(wrapper.findAll('button')[0]?.attributes('disabled')).toBeDefined()
  })
})
