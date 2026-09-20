// @vitest-environment happy-dom

/** API Key 汇总表的列结构与操作事件回归测试。 */
import type { CompanyApiKey } from '@/api/apiKeys'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ApiKeyTable from './index.vue'

/** 固定一条完整用量数据，确保所有列都会进入真实数据分支。 */
const companyKey: CompanyApiKey = {
  id: '9',
  tenant_id: '3',
  tenant_name: '客户 A',
  name: '生产 Key',
  key_prefix: 'rmk_masked',
  token_limit: 1000,
  token_used: 34,
  token_reserved: 0,
  token_remaining: 966,
  prompt_tokens: 26,
  completion_tokens: 8,
  status: 'active',
  expires_at: null,
  last_used_at: '2026-09-20T00:00:00Z',
  created_at: '2026-09-20T00:00:00Z',
  revoked_at: null,
}

describe('api key table', () => {
  it('keeps flex content inside seven fixed table cells', () => {
    const wrapper = mount(ApiKeyTable, {
      props: { items: [companyKey], loading: false, busyId: '' },
    })
    const cells = wrapper.findAll('tbody tr td')

    expect(wrapper.findAll('colgroup col')).toHaveLength(7)
    expect(cells).toHaveLength(7)
    expect(cells[1]?.find('.api-key-prefix-content').exists()).toBe(true)
    expect(cells[6]?.find('.api-key-action-list').exists()).toBe(true)
    expect(cells[1]?.classes()).not.toContain('api-key-prefix-content')
    expect(cells[6]?.classes()).not.toContain('api-key-action-list')
  })
})
