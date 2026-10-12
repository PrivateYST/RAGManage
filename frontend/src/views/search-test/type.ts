import type { ComputedRef, Ref, ShallowRef } from 'vue'
import type { KnowledgeBaseRow } from '@/api/admin'
import type { SearchTestResult } from '@/api/search'

/** 检索调试页面对模板公开的状态和操作契约。 */
export interface SearchTestState {
  knowledgeBases: Ref<KnowledgeBaseRow[]>
  knowledgeBaseId: ShallowRef<string>
  selectedKnowledgeBase: ComputedRef<KnowledgeBaseRow | null>
  query: ShallowRef<string>
  topK: ShallowRef<number>
  contextMaxChars: ShallowRef<number>
  loadingKnowledgeBases: ShallowRef<boolean>
  searching: ShallowRef<boolean>
  errorMessage: ShallowRef<string>
  canSearch: ComputedRef<boolean>
  result: ShallowRef<SearchTestResult | null>
  loadKnowledgeBases: () => Promise<void>
  search: () => Promise<void>
}
