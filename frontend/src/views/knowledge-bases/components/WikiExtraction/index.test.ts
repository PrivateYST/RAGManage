// @vitest-environment happy-dom
/** 真实表格渲染与导入回归，防止预览有数据但未注册表格导致无法选择。 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import WikiExtraction from './index.vue'

const api = vi.hoisted(() => ({
  previewWikiExtraction: vi.fn(),
  importWikiExtraction: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))
vi.mock('@/api/wiki', () => api)
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: api.success, error: api.error }),
}))

/** 用可追溯的源片段驱动真实 AppTable；不模拟本次要验证的表格。 */
function setup() {
  return mount(WikiExtraction, {
    props: {
      knowledgeBaseId: '4',
      options: {
        members: [{ id: '1', display_name: '管理员' }],
        sources: [],
        documents: [{ id: '7', title: '原文' }],
      },
    },
    global: { stubs: { RouterLink: true } },
  })
}

describe('document extraction workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.previewWikiExtraction.mockResolvedValue({
      release_id: '5',
      document_version_id: '7',
      document_title: '原文',
      method: 'document_sections',
      notice: '需审核',
      items: [
        {
          key: 'abc',
          term: '儿童健康',
          definition: '原文内容',
          aliases: [],
          existing: false,
          warning: '',
          sources: [
            { chunk_id: '33', document_id: '7', document_version_id: '7', locator: { page: 33 } },
          ],
        },
      ],
    })
    api.importWikiExtraction.mockResolvedValue({ items: [{ id: '26' }], skipped: [] })
  })
  it('renders selectable preview without writing, then imports only selected drafts', async () => {
    const wrapper = setup()
    await wrapper.get('[aria-label="自动生成来源文档"]').setValue('7')
    await wrapper.get('[aria-label="自动生成负责人"]').setValue('1')
    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()
    expect(api.importWikiExtraction).not.toHaveBeenCalled()
    await wrapper.get('[aria-label="选择候选：儿童健康"]').setValue(true)
    const save = wrapper.findAll('button').find((b) => b.text().includes('保存 1 条草稿'))!
    await save.trigger('click')
    await flushPromises()
    expect(api.importWikiExtraction).toHaveBeenCalledWith('4', {
      document_id: 7,
      release_id: 5,
      document_version_id: 7,
      candidate_keys: ['abc'],
      owner_user_id: 1,
    })
    expect(wrapper.emitted('imported')).toHaveLength(1)
    expect(wrapper.get('[aria-label="选择候选：儿童健康"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
  it('keeps the selection after import failure and allows retry', async () => {
    const wrapper = setup()
    await wrapper.get('[aria-label="自动生成来源文档"]').setValue('7')
    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()
    await wrapper.get('[aria-label="选择候选：儿童健康"]').setValue(true)
    api.importWikiExtraction.mockRejectedValueOnce(new Error('版本已变化'))
    const save = wrapper.findAll('button').find((b) => b.text().includes('保存 1 条草稿'))!
    await save.trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toBe('版本已变化')
    expect(
      (wrapper.get('[aria-label="选择候选：儿童健康"]').element as HTMLInputElement).checked,
    ).toBe(true)
    expect(wrapper.emitted('imported')).toBeUndefined()
    wrapper.unmount()
  })
})
