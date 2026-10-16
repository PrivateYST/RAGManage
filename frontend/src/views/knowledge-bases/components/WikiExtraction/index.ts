/** 文档章节预览与批量草稿导入，失败保留选择，版本冲突要求重新预览。 */
import type { WikiExtractionProps } from './type'
import type { WikiCandidate, WikiExtractionPreview } from '@/api/wiki'
import type { AppTableColumn } from '@/components'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { importWikiExtraction, previewWikiExtraction } from '@/api/wiki'
import { useAppToast } from '@/composables/useToast'

/** 候选使用统一业务表格，不另建分页能力。 */
export const columns: AppTableColumn<WikiCandidate>[] = [
  { key: 'select', title: '选择', width: '60px' },
  { key: 'term', title: '候选词条', width: '230px' },
  { key: 'definition', title: '原文摘要' },
  { key: 'sources', title: '来源', width: '160px' },
]

/** 预览不会创建事实，显式选择后才原子导入草稿。 */
export function useWikiExtraction(
  props: WikiExtractionProps,
  imported: () => void,
  busyChanged: (value: boolean) => void,
) {
  const toast = useAppToast()
  const documentId = ref('')
  const ownerId = ref('')
  const busy = ref(false)
  const importing = ref(false)
  // 导入时锁定父容器标签，防止卸载后成功事件丢失而列表仍显示旧数据。
  watch(() => busy.value || importing.value, busyChanged, { flush: 'sync' })
  onScopeDispose(() => busyChanged(false))
  const error = ref('')
  const preview = ref<WikiExtractionPreview | null>(null)
  const selected = ref<string[]>([])
  const documents = computed(
    () =>
      props.options.documents ?? [
        ...new Map(
          props.options.sources.map((s) => [
            s.document_id,
            { id: s.document_id, title: s.document_title },
          ]),
        ).values(),
      ],
  )
  const candidates = computed(() => preview.value?.items ?? [])
  const available = computed(() => candidates.value.filter((c) => !c.existing))
  /** 文档改变撤销旧预览，防止跨文档误导入。 */
  watch(documentId, () => {
    preview.value = null
    selected.value = []
    error.value = ''
  })
  /** 生成显示进行中状态，失败可保留文档重试。 */
  async function generate() {
    if (!documentId.value || busy.value || importing.value) return
    busy.value = true
    error.value = ''
    preview.value = null
    selected.value = []
    try {
      preview.value = await previewWikiExtraction(props.knowledgeBaseId, documentId.value)
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '生成预览失败'
      toast.error(error.value)
    } finally {
      busy.value = false
    }
  }
  /** 全选只包含尚未存在的候选。 */
  function selectAll() {
    selected.value = available.value.map((c) => c.key)
  }
  /** 使用稳定候选键，选择不依赖当前分页行号。 */
  function toggle(key: string) {
    selected.value = selected.value.includes(key)
      ? selected.value.filter((k) => k !== key)
      : [...selected.value, key]
  }
  /** 成功后标记已创建条目；失败保留选择供重试。 */
  async function save() {
    if (!preview.value || !selected.value.length || importing.value) return
    importing.value = true
    error.value = ''
    try {
      const result = await importWikiExtraction(props.knowledgeBaseId, {
        document_id: Number(documentId.value),
        release_id: Number(preview.value.release_id),
        document_version_id: Number(preview.value.document_version_id),
        candidate_keys: selected.value,
        owner_user_id: ownerId.value ? Number(ownerId.value) : null,
      })
      for (const candidate of candidates.value) {
        if (selected.value.includes(candidate.key)) candidate.existing = true
      }
      selected.value = []
      toast.success(
        `已生成 ${result.items.length} 条草稿，跳过 ${result.skipped.length} 条重复词条`,
      )
      imported()
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '导入草稿失败'
      toast.error(error.value)
    } finally {
      importing.value = false
    }
  }
  return {
    documentId,
    ownerId,
    busy,
    importing,
    error,
    preview,
    selected,
    documents,
    candidates,
    available,
    generate,
    selectAll,
    toggle,
    save,
  }
}
