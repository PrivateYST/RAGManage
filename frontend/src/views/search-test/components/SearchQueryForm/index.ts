import type { ComputedRef, Ref } from 'vue'
import type { SearchQueryFormProps } from './type'
import { computed } from 'vue'

/** 根据当前目标和请求状态生成表单的运行提示，不触发副作用。 */
export function useSearchQueryForm(
  props: SearchQueryFormProps,
  knowledgeBaseId: Ref<string>,
  query: Ref<string>,
): { searchActionHint: ComputedRef<string> } {
  const selectedKnowledgeBase = computed(() =>
    props.knowledgeBases.find((item) => item.id === knowledgeBaseId.value),
  )

  const searchActionHint = computed(() => {
    if (props.loading) return '正在加载知识库和发布版本…'
    if (!props.knowledgeBases.length) return '当前空间暂无知识库'
    if (!knowledgeBaseId.value) return '请先选择目标知识库'
    if (!selectedKnowledgeBase.value?.active_release_id)
      return '该知识库尚未发布 Release，发布后才能检索'
    if (!query.value.trim()) return '请输入测试问题后运行检索'
    if (props.searching) return '正在当前 Release 中执行融合检索…'
    return '将在当前 Release 中融合召回证据，不会生成回答'
  })

  return { searchActionHint }
}
