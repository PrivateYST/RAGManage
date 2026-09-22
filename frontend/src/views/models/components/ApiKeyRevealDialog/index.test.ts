// @vitest-environment happy-dom

/** 一次性明文 API Key 的复制成功与浏览器权限失败反馈测试。 */
import type { CreatedApiKey } from '@/api/apiKeys'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { toastKey } from '@/composables/useToast'
import ApiKeyRevealDialog from './index.vue'

const apiKey: CreatedApiKey = {
  id: '9',
  tenant_id: '3',
  tenant_name: '客户 A',
  name: '生产 Key',
  provider: 'open_webui',
  key_prefix: 'rmk_masked',
  raw_key: 'rmk_once_only_secret',
  token_limit: 1000,
  token_used: 0,
  token_reserved: 0,
  token_remaining: 1000,
  prompt_tokens: 0,
  completion_tokens: 0,
  status: 'active',
  expires_at: null,
  last_used_at: null,
  created_at: '2026-09-20T00:00:00Z',
  revoked_at: null,
}

describe('api key reveal dialog', () => {
  const writeText = vi.fn()
  const toastError = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
  })

  it('copies the one-time plaintext and reports success to the manager', async () => {
    writeText.mockResolvedValue(undefined)
    const wrapper = mount(ApiKeyRevealDialog, {
      props: { apiKey },
      global: {
        provide: {
          [toastKey as symbol]: {
            error: toastError,
            success: vi.fn(),
            info: vi.fn(),
            show: vi.fn(),
          },
        },
      },
    })
    await flushPromises()

    const copyButton = document.body.querySelector<HTMLButtonElement>('.api-key-raw-value button')
    expect(copyButton).not.toBeNull()
    copyButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()

    expect(writeText).toHaveBeenCalledWith('rmk_once_only_secret')
    expect(wrapper.emitted('copied')).toHaveLength(1)
    expect(toastError).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps the key visible and explains clipboard permission failures', async () => {
    writeText.mockRejectedValue(new Error('permission denied'))
    const wrapper = mount(ApiKeyRevealDialog, {
      props: { apiKey },
      global: {
        provide: {
          [toastKey as symbol]: {
            error: toastError,
            success: vi.fn(),
            info: vi.fn(),
            show: vi.fn(),
          },
        },
      },
    })
    await flushPromises()

    const copyButton = document.body.querySelector<HTMLButtonElement>('.api-key-raw-value button')
    expect(copyButton).not.toBeNull()
    copyButton?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()

    expect(toastError).toHaveBeenCalledWith('复制失败', '请手动选择并复制 API Key。')
    expect(document.body.textContent).toContain('rmk_once_only_secret')
    expect(wrapper.emitted('copied')).toBeUndefined()
    expect(document.body.querySelector('.api-key-raw-value button')?.hasAttribute('disabled')).toBe(
      false,
    )
    wrapper.unmount()
  })
})
