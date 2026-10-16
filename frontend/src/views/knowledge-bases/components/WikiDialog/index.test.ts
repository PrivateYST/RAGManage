// @vitest-environment happy-dom
/** Wiki 管理回归：打开即加载、持久化完整来源、版本冲突重试和只读权限。 */
import type { WikiEntry } from '@/api/wiki'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, reactive } from 'vue'
import { useWikiDialog } from './index'

const api = vi.hoisted(() => ({
  fetchWikiEntries: vi.fn(),
  fetchWikiOptions: vi.fn(),
  createWikiEntry: vi.fn(),
  updateWikiEntry: vi.fn(),
  transitionWikiEntry: vi.fn(),
  fetchWikiRevisions: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))
vi.mock('@/api/wiki', () => api)
vi.mock('@/composables/useToast', () => ({
  useAppToast: () => ({ success: api.success, error: api.error }),
}))

/** 使用与实际 API 相同的词条结构，版本递增由服务端负责。 */
function entry(): WikiEntry {
  return {
    id: '1',
    knowledge_base_id: '9',
    term: '儿童健康',
    definition: '规范定义',
    aliases: ['儿保'],
    status: 'draft',
    version_no: 2,
    owner_user_id: '7',
    valid_from: null,
    valid_until: null,
    updated_at: '2026-10-16T00:00:00Z',
    sources: [
      {
        chunk_id: '21',
        document_id: '3',
        document_version_id: '4',
        document_title: '规范',
        version_no: 1,
        content: '服务内容',
        locator: { page: 33 },
        note: '规范第33页',
      },
    ],
  }
}

/** 在 Vue 作用域中安装 watcher，测试后统一释放。 */
function setup() {
  const scope = effectScope()
  const props = reactive({ open: true, knowledgeBaseId: '9', knowledgeBaseName: '公共卫生规范' })
  const page = scope.run(() => useWikiDialog(props))!
  return { page, scope, props }
}

describe('lLM Wiki lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.fetchWikiEntries.mockResolvedValue({ items: [entry()], can_manage: true })
    api.fetchWikiOptions.mockResolvedValue({
      members: [{ id: '7', display_name: '负责人' }],
      sources: entry().sources,
    })
    api.createWikiEntry.mockResolvedValue(entry())
    api.updateWikiEntry.mockResolvedValue(entry())
    api.transitionWikiEntry.mockResolvedValue(entry())
    api.fetchWikiRevisions.mockResolvedValue({ items: [] })
  })

  it('loads on first mount and retains all source details on edit', async () => {
    const { page, scope } = setup()
    await vi.waitFor(() => expect(page.entries.value).toHaveLength(1))
    expect(api.fetchWikiEntries).toHaveBeenCalledWith('9')
    // 首次打开只展示列表，显式编辑才出现表单，保存后应返回列表。
    expect(page.formOpen.value).toBe(false)
    page.edit(entry())
    expect(page.formOpen.value).toBe(true)
    await page.save()
    expect(api.updateWikiEntry).toHaveBeenCalledWith(
      '1',
      expect.objectContaining({
        expected_version: 2,
        aliases: ['儿保'],
        owner_user_id: 7,
        sources: [{ chunk_id: 21, note: '规范第33页' }],
      }),
    )
    expect(page.editing.value).toBe(false)
    expect(page.formOpen.value).toBe(false)
    expect(api.fetchWikiEntries).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('keeps the draft when a stale version is rejected and permits retry', async () => {
    const { page, scope } = setup()
    await vi.waitFor(() => expect(page.entries.value).toHaveLength(1))
    page.edit(entry())
    api.updateWikiEntry.mockRejectedValueOnce(new Error('词条已被修改，请刷新后重试'))
    await page.save()
    expect(page.draft.value.term).toBe('儿童健康')
    expect(page.editing.value).toBe(true)
    expect(page.saving.value).toBe(false)
    expect(api.error).toHaveBeenCalledWith('词条已被修改，请刷新后重试')
    scope.stop()
  })

  it('submits the selected status and refreshes persisted state', async () => {
    const { page, scope } = setup()
    await vi.waitFor(() => expect(page.entries.value).toHaveLength(1))
    await page.transition(entry(), 'review')
    expect(api.transitionWikiEntry).toHaveBeenCalledWith(entry(), 'review')
    expect(api.fetchWikiEntries).toHaveBeenCalledTimes(2)
    scope.stop()
  })

  it('does not request administrator options for readers', async () => {
    api.fetchWikiEntries.mockResolvedValue({ items: [], can_manage: false })
    const { page, scope } = setup()
    await vi.waitFor(() => expect(page.loading.value).toBe(false))
    expect(page.canManage.value).toBe(false)
    expect(api.fetchWikiOptions).not.toHaveBeenCalled()
    scope.stop()
  })
})
