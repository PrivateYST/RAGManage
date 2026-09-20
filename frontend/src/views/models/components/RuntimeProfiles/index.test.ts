// @vitest-environment happy-dom

import type { EmbeddingProfile, ModelEndpoint, RuntimeProfile } from '@/api/models'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RuntimeProfiles from './index.vue'

const embedding: EmbeddingProfile = {
  id: '8',
  model_endpoint_id: '2',
  endpoint_name: '嵌入网关',
  endpoint_status: 'active',
  model_name: 'qwen3-embedding:0.6b',
  model_revision: 'digest',
  dimension: 1024,
  dtype: 'float32',
  instructions: {},
  normalization: 'l2',
  definition_hash: 'a'.repeat(64),
  created_at: '2026-09-19T00:00:00Z',
  effect_scope: 'rebuild_required',
}
const generation: ModelEndpoint = {
  id: '3',
  tenant_id: null,
  name: '生成网关',
  provider: 'open_webui',
  endpoint_type: 'generation',
  base_url: 'http://gateway.internal:8080',
  allowed_models: ['qwen3.8:27b'],
  health_status: 'healthy',
  status: 'active',
  last_checked_at: null,
  last_latency_ms: null,
  last_error: null,
  observed_dimension: null,
  secret_configured: true,
  created_at: '',
  updated_at: '',
}
const runtime: RuntimeProfile = {
  id: '21',
  embedding_profile_id: '8',
  definition: {
    retrieval: { top_k: 10, context_max_chars: 8000 },
    generation: { endpoint_id: 3, model: 'qwen3.8:27b', temperature: 0.2 },
  },
  definition_hash: 'b'.repeat(64),
  created_at: '',
  active: false,
  effect_scope: 'activate_required',
}

describe('runtime profiles', () => {
  it('exposes activation for an immutable inactive version', async () => {
    const wrapper = mount(RuntimeProfiles, {
      props: {
        items: [runtime],
        embeddingProfiles: [embedding],
        endpoints: [generation],
        busyId: '',
      },
    })

    expect(wrapper.text()).toContain('换嵌入需重建')
    const activate = wrapper.findAll('button').find(button => button.text().includes('激活'))
    await activate?.trigger('click')
    expect(wrapper.emitted('activate')?.[0]).toEqual(['21'])
  })
})
