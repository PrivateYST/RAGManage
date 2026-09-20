import type { KnowledgeBaseRow } from '@/api/admin'
import type { SearchTestResult } from '@/api/search'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '@/api/admin'
import { runSearchTest } from '@/api/search'
import { useAuthStore } from '@/store/auth'

export function useSearchTest() {
  const auth = useAuthStore()
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const knowledgeBaseId = shallowRef('')
  const query = shallowRef('')
  const topK = shallowRef(10)
  const contextMaxChars = shallowRef(6000)
  const loadingKnowledgeBases = shallowRef(true)
  const searching = shallowRef(false)
  const error = shallowRef('')
  const result = shallowRef<SearchTestResult | null>(null)

  const selectedKnowledgeBase = computed(
    () => knowledgeBases.value.find(item => item.id === knowledgeBaseId.value) ?? null,
  )
  const canSearch = computed(
    () =>
      Boolean(selectedKnowledgeBase.value?.active_release_id && query.value.trim())
      && !loadingKnowledgeBases.value
      && !searching.value,
  )

  async function loadKnowledgeBases(): Promise<void> {
    loadingKnowledgeBases.value = true
    error.value = ''
    result.value = null
    try {
      if (!auth.activeSpaceId) {
        knowledgeBases.value = []
        knowledgeBaseId.value = ''
        return
      }
      knowledgeBases.value = (await fetchKnowledgeBases(auth.activeSpaceId)).items
      if (!knowledgeBases.value.some(item => item.id === knowledgeBaseId.value)) {
        knowledgeBaseId.value
          = knowledgeBases.value.find(item => item.active_release_id)?.id
            ?? knowledgeBases.value[0]?.id
            ?? ''
      }
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '知识库加载失败'
    }
    finally {
      loadingKnowledgeBases.value = false
    }
  }

  async function search(): Promise<void> {
    const trimmedQuery = query.value.trim()
    if (!knowledgeBaseId.value || !trimmedQuery || searching.value)
      return
    searching.value = true
    error.value = ''
    result.value = null
    try {
      result.value = await runSearchTest({
        knowledge_base_id: Number(knowledgeBaseId.value),
        query: trimmedQuery,
        top_k: topK.value,
        context_max_chars: contextMaxChars.value,
      })
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '检索运行失败'
    }
    finally {
      searching.value = false
    }
  }

  watch(() => auth.activeSpaceId, loadKnowledgeBases, { immediate: true })

  return {
    knowledgeBases,
    knowledgeBaseId,
    selectedKnowledgeBase,
    query,
    topK,
    contextMaxChars,
    loadingKnowledgeBases,
    searching,
    canSearch,
    error,
    result,
    loadKnowledgeBases,
    search,
  }
}
