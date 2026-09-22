// @vitest-environment happy-dom

/** API Key 管理工作区的加载、创建、用量、状态和删除闭环测试。 */
import type { ApiKeyUsageResponse, CompanyApiKey, CreatedApiKey } from '@/api/apiKeys'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ApiKeyManager from './index.vue'

const apiMocks = vi.hoisted(() => ({
  createApiKey: vi.fn(),
  fetchApiKeys: vi.fn(),
  fetchApiKeyUsage: vi.fn(),
  deleteApiKey: vi.fn(),
  updateApiKeyStatus: vi.fn(),
  fetchTenants: vi.fn(),
}))

vi.mock('@/api/apiKeys', () => ({
  createApiKey: apiMocks.createApiKey,
  fetchApiKeys: apiMocks.fetchApiKeys,
  fetchApiKeyUsage: apiMocks.fetchApiKeyUsage,
  deleteApiKey: apiMocks.deleteApiKey,
  updateApiKeyStatus: apiMocks.updateApiKeyStatus,
}))
vi.mock('@/api/admin', () => ({ fetchTenants: apiMocks.fetchTenants }))

const companyKey: CompanyApiKey = {
  id: '9',
  tenant_id: '3',
  tenant_name: '客户 A',
  name: '生产 Key',
  provider: 'local',
  key_prefix: 'sk-masked',
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

const createdKey: CreatedApiKey = { ...companyKey, raw_key: 'sk-once-only-secret' }
const secondCompanyKey: CompanyApiKey = {
  ...companyKey,
  id: '10',
  name: '备用 Key',
  key_prefix: 'sk-second',
}

/** 创建可手动决定返回顺序的 Promise，用于复现快速切换时的网络竞态。 */
function deferredUsage() {
  let resolve!: (value: ApiKeyUsageResponse) => void
  const promise = new Promise<ApiKeyUsageResponse>((promiseResolve) => {
    resolve = promiseResolve
  })
  return { promise, resolve }
}

describe('api key manager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.fetchApiKeys.mockResolvedValue({ items: [companyKey] })
    apiMocks.fetchTenants.mockResolvedValue({
      items: [
        {
          id: '3',
          code: 'customer-a',
          name: '客户 A',
          status: 'active',
          member_count: 1,
          knowledge_base_count: 1,
          created_at: '2026-09-20T00:00:00Z',
        },
      ],
    })
    apiMocks.createApiKey.mockResolvedValue(createdKey)
    apiMocks.deleteApiKey.mockResolvedValue({ id: '9', name: '生产 Key', status: 'revoked' })
    apiMocks.updateApiKeyStatus.mockResolvedValue({ id: '9', name: '生产 Key', status: 'disabled' })
    apiMocks.fetchApiKeyUsage.mockResolvedValue({
      summary: {
        request_count: 350,
        prompt_tokens: 2600,
        completion_tokens: 900,
        total_tokens: 3500,
      },
      recent_limit: 200,
      items: [
        {
          request_id: '11111111-1111-4111-8111-111111111111',
          model_name: 'embed + chat',
          prompt_tokens: 26,
          completion_tokens: 8,
          total_tokens: 34,
          usage_source: 'gateway',
          model_usage: {
            embedding: {
              model: 'embed',
              prompt_tokens: 6,
              completion_tokens: 0,
              total_tokens: 6,
              usage_source: 'gateway',
            },
            generation: {
              model: 'chat',
              prompt_tokens: 20,
              completion_tokens: 8,
              total_tokens: 28,
              usage_source: 'gateway',
            },
          },
          status: 'completed',
          created_at: '2026-09-20T00:00:00Z',
          completed_at: '2026-09-20T00:00:01Z',
        },
      ],
    })
  })

  it('loads keys and displays cumulative input and output usage', async () => {
    const wrapper = mount(ApiKeyManager)
    await flushPromises()

    expect(wrapper.text()).toContain('客户 A')
    expect(wrapper.text()).toContain('26')
    expect(wrapper.text()).toContain('8')
    expect(apiMocks.fetchApiKeys).toHaveBeenCalledOnce()
  })

  it('creates a key and shows its plaintext exactly in the one-time dialog', async () => {
    const wrapper = mount(ApiKeyManager)
    await flushPromises()
    const createButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('生成医院网关 Key'))
    await createButton?.trigger('click')

    const form = document.body.querySelector<HTMLFormElement>('.api-key-form')
    expect(form).not.toBeNull()
    const inputs = form?.querySelectorAll<HTMLInputElement>('input') ?? []
    inputs[0].value = '测试 Key'
    inputs[0].dispatchEvent(new Event('input', { bubbles: true }))
    inputs[1].value = '2000'
    inputs[1].dispatchEvent(new Event('input', { bubbles: true }))
    form?.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(apiMocks.createApiKey).toHaveBeenCalledWith({
      tenant_id: 3,
      name: '测试 Key',
      token_limit: 2000,
      expires_at: null,
    })
    expect(document.body.textContent).toContain('sk-once-only-secret')
    expect(document.body.textContent).toContain('仅显示一次')
  })

  it('loads per-model usage and requires confirmation before deleting', async () => {
    const wrapper = mount(ApiKeyManager)
    await flushPromises()
    const usageButton = wrapper.findAll('button').find((button) => button.text().includes('用量'))
    await usageButton?.trigger('click')
    await flushPromises()

    expect(apiMocks.fetchApiKeyUsage).toHaveBeenCalledWith('9')
    expect(wrapper.text()).toContain('3,500')
    expect(wrapper.text()).toContain('共 350 条')
    expect(wrapper.text()).toContain('嵌入 6')
    expect(wrapper.text()).toContain('生成 28')

    const deleteButton = wrapper.findAll('button').find((button) => button.text().includes('删除'))
    await deleteButton?.trigger('click')
    expect(apiMocks.deleteApiKey).not.toHaveBeenCalled()
    const alertDialog = document.body.querySelector('[role="alertdialog"]')
    expect(alertDialog?.textContent).toContain('确认删除“生产 Key”')

    const confirmButton = Array.from(alertDialog?.querySelectorAll('button') ?? []).find(
      (button) => button.textContent?.trim() === '确认删除',
    )
    confirmButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(apiMocks.deleteApiKey).toHaveBeenCalledWith('9')
  })

  it('toggles key status through the backend and refreshes the list', async () => {
    const wrapper = mount(ApiKeyManager)
    await flushPromises()
    const statusButton = wrapper.findAll('button').find((button) => button.text().includes('启用'))
    await statusButton?.trigger('click')
    expect(apiMocks.updateApiKeyStatus).not.toHaveBeenCalled()
    const alertDialog = document.body.querySelector('[role="alertdialog"]')
    expect(alertDialog?.textContent).toContain('确认停用')
    const confirmButton = Array.from(alertDialog?.querySelectorAll('button') ?? []).find(
      (button) => button.textContent?.trim() === '确认停用',
    )
    confirmButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()

    expect(apiMocks.updateApiKeyStatus).toHaveBeenCalledWith('9', 'disabled')
  })

  it('keeps the newest key selected when an older usage request resolves last', async () => {
    const first = deferredUsage()
    const second = deferredUsage()
    apiMocks.fetchApiKeys.mockResolvedValue({ items: [companyKey, secondCompanyKey] })
    apiMocks.fetchApiKeyUsage.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const wrapper = mount(ApiKeyManager)
    await flushPromises()
    const usageButtons = wrapper
      .findAll('button')
      .filter((button) => button.text().includes('用量'))

    await usageButtons[0]?.trigger('click')
    await usageButtons[1]?.trigger('click')
    expect(wrapper.text()).toContain('备用 Key · Token 用量')
    expect(wrapper.text()).toContain('正在加载用量')

    second.resolve({
      summary: { request_count: 1, prompt_tokens: 20, completion_tokens: 5, total_tokens: 25 },
      recent_limit: 200,
      items: [],
    })
    await flushPromises()
    first.resolve({
      summary: { request_count: 99, prompt_tokens: 990, completion_tokens: 9, total_tokens: 999 },
      recent_limit: 200,
      items: [],
    })
    await flushPromises()

    expect(wrapper.text()).toContain('备用 Key · Token 用量')
    expect(wrapper.text()).toContain('共 1 条')
    expect(wrapper.text()).not.toContain('共 99 条')
  })
})
