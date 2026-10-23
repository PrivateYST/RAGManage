/** 词条管理状态与异步操作；隔离弹窗切换、保存冲突和历史查询反馈。 */
import type { WikiDialogProps } from './type'
import type { WikiEntry, WikiOptions, WikiPayload, WikiRevision, WikiStatus } from '@/api/wiki'
import { computed, ref, shallowRef, watch } from 'vue'
import {
  createWikiEntry,
  fetchWikiEntries,
  fetchWikiOptions,
  fetchWikiRevisions,
  transitionWikiEntry,
  updateWikiEntry,
} from '@/api/wiki'
import { useAppToast } from '@/composables/useToast'

/** 草稿只保留 API 定义的可编辑内容，避免把状态和审计字段带入保存请求。 */
function emptyDraft(): WikiPayload {
  return {
    term: '',
    definition: '',
    aliases: [],
    owner_user_id: null,
    valid_from: null,
    valid_until: null,
    sources: [],
  }
}

/** 列表、编辑和版本历史共用当前知识库；服务端仍是权限最终判定方。 */
export function useWikiDialog(props: WikiDialogProps) {
  const toast = useAppToast()
  const entries = ref<WikiEntry[]>([])
  const options = ref<WikiOptions>({ members: [], sources: [] })
  const canManage = shallowRef(false)
  const loading = shallowRef(false)
  const saving = shallowRef(false)
  const error = shallowRef('')
  const editingEntry = ref<WikiEntry | null>(null)
  // 默认只看词条列表，显式新建或编辑才展示表单，避免整张长表单占据管理视图。
  const formOpen = shallowRef(false)
  // 子视图复用同一知识库权限和真实词条状态。
  const view = ref<'list' | 'graph' | 'extract'>('list')
  const extractionBusy = ref(false)
  const draft = ref<WikiPayload>(emptyDraft())
  const revisions = ref<WikiRevision[]>([])
  const historyTerm = shallowRef('')
  const sourceQuery = shallowRef('')
  const searching = shallowRef(false)
  const editing = computed(() => editingEntry.value !== null)
  const pendingPublicationCount = computed(
    () =>
      entries.value.filter((entry) => entry.status === 'draft' || entry.status === 'review').length,
  )
  const publishedCount = computed(
    () => entries.value.filter((entry) => entry.status === 'published').length,
  )
  const retiredCount = computed(
    () => entries.value.filter((entry) => entry.status === 'retired').length,
  )
  let loadSerial = 0

  /** 保存后清空局部编辑状态，取消时也可回到新增。 */
  function reset(): void {
    editingEntry.value = null
    draft.value = emptyDraft()
    formOpen.value = false
  }

  /** 新建与编辑共用表单，但每次新建都清除上一次的版本和来源。 */
  function startCreate(): void {
    reset()
    historyTerm.value = ''
    formOpen.value = true
    view.value = 'list'
  }

  /** 打开时并行之外先取权限，避免只读用户访问管理员选项接口。 */
  async function load(): Promise<void> {
    const serial = ++loadSerial
    loading.value = true
    error.value = ''
    try {
      const result = await fetchWikiEntries(props.knowledgeBaseId)
      if (serial !== loadSerial) return
      entries.value = result.items
      canManage.value = result.can_manage
      const nextOptions = result.can_manage
        ? await fetchWikiOptions(props.knowledgeBaseId)
        : { members: [], sources: [] }
      if (serial === loadSerial) options.value = nextOptions
    } catch (cause) {
      if (serial === loadSerial)
        error.value = cause instanceof Error ? cause.message : '词条加载失败'
    } finally {
      if (serial === loadSerial) loading.value = false
    }
  }

  /** 在当前发布版本中按正文搜索原文，让来源选择无需知道内部 ID。 */
  async function searchSources(): Promise<void> {
    searching.value = true
    try {
      options.value = await fetchWikiOptions(props.knowledgeBaseId, sourceQuery.value)
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '原文搜索失败')
    } finally {
      searching.value = false
    }
  }

  /** 编辑时保留完整来源列表，禁止只保存第一条导致其他关联丢失。 */
  function edit(entry: WikiEntry): void {
    formOpen.value = true
    view.value = 'list'
    historyTerm.value = ''
    editingEntry.value = entry
    draft.value = {
      term: entry.term,
      definition: entry.definition,
      aliases: [...entry.aliases],
      owner_user_id: entry.owner_user_id ? Number(entry.owner_user_id) : null,
      valid_from: entry.valid_from,
      valid_until: entry.valid_until,
      sources: entry.sources
        .filter((source) => source.chunk_id)
        .map((source) => ({ chunk_id: Number(source.chunk_id), note: source.note || '' })),
      expected_version: entry.version_no,
    }
    // 保留旧来源预览；失效来源仍须在服务端验证后才能再次发布。
    const known = new Set(options.value.sources.map((source) => source.chunk_id))
    options.value.sources.push(...entry.sources.filter((source) => !known.has(source.chunk_id)))
  }

  /** 错误时保留草稿，成功后重新读取持久化状态和权限。 */
  async function save(): Promise<void> {
    if (saving.value) return
    saving.value = true
    try {
      const payload = {
        ...draft.value,
        valid_from: draft.value.valid_from || null,
        valid_until: draft.value.valid_until || null,
      }
      if (editingEntry.value) await updateWikiEntry(editingEntry.value.id, payload)
      else await createWikiEntry(props.knowledgeBaseId, payload)
      toast.success('词条草稿已保存，送审发布后参与检索')
      reset()
      await load()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '词条保存失败')
    } finally {
      saving.value = false
    }
  }

  /** 状态迁移有冲突时保留页面，让用户明确刷新后重试。 */
  async function transition(entry: WikiEntry, status: WikiStatus): Promise<void> {
    if (saving.value) return
    saving.value = true
    try {
      await transitionWikiEntry(entry, status)
      if (entry.status === 'retired' && status === 'published') {
        toast.success('词条已启用并参与检索')
      } else if (status === 'published') {
        toast.success('词条已审核发布并参与检索')
      } else if (status === 'retired') {
        toast.success('词条已停用并退出检索')
      } else {
        toast.success('词条状态已更新')
      }
      await load()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '状态更新失败')
    } finally {
      saving.value = false
    }
  }

  /** 按词条状态批量迁移当前知识库全部匹配项，并汇报部分成功以便重试失败项。 */
  async function bulkTransition(action: 'publish' | 'retire' | 'enable'): Promise<void> {
    if (saving.value) return
    const eligible = entries.value.filter((entry) => {
      if (action === 'publish') return entry.status === 'draft' || entry.status === 'review'
      if (action === 'retire') return entry.status === 'published'
      return entry.status === 'retired'
    })
    if (!eligible.length) return

    const target: WikiStatus = action === 'retire' ? 'retired' : 'published'
    saving.value = true
    try {
      const results = await Promise.allSettled(
        eligible.map((entry) => transitionWikiEntry(entry, target)),
      )
      const failed = results.flatMap((result, index) =>
        result.status === 'rejected' ? [eligible[index]] : [],
      )
      const succeeded = eligible.length - failed.length

      if (failed.length) {
        const failedNames = failed
          .slice(0, 3)
          .map((entry) => entry.term)
          .join('、')
        const more = failed.length > 3 ? `等 ${failed.length} 条` : failedNames
        const reason = results.find((result) => result.status === 'rejected')
        const detail =
          reason?.status === 'rejected' && reason.reason instanceof Error
            ? reason.reason.message
            : '请刷新后重试'
        toast.error(`${succeeded} 条成功，${failed.length} 条失败（${more}）：${detail}`)
      } else if (action === 'publish') {
        toast.success(`已审核发布 ${succeeded} 条词条并参与检索`)
      } else if (action === 'retire') {
        toast.success(`已停用 ${succeeded} 条词条并退出检索`)
      } else {
        toast.success(`已启用 ${succeeded} 条词条并参与检索`)
      }
      await load()
    } finally {
      saving.value = false
    }
  }

  /** 历史快照由独立接口读取，不把未审核历史暴露给普通读者。 */
  async function showHistory(entry: WikiEntry): Promise<void> {
    try {
      const result = await fetchWikiRevisions(entry.id)
      revisions.value = result.items
      historyTerm.value = entry.term
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '版本历史加载失败')
    }
  }

  watch(
    () => [props.open, props.knowledgeBaseId] as const,
    ([open]) => {
      loadSerial++
      if (open) {
        reset()
        view.value = 'list'
        historyTerm.value = ''
        sourceQuery.value = ''
        void load()
      }
    },
    { immediate: true },
  )

  return {
    entries,
    options,
    canManage,
    loading,
    saving,
    error,
    editingEntry,
    draft,
    revisions,
    historyTerm,
    sourceQuery,
    searching,
    editing,
    pendingPublicationCount,
    publishedCount,
    retiredCount,
    formOpen,
    startCreate,
    view,
    extractionBusy,
    load,
    reset,
    edit,
    searchSources,
    save,
    transition,
    bulkTransition,
    showHistory,
  }
}
