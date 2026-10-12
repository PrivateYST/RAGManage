/** 对话工作区页面级状态和操作契约。 */
import type { ComputedRef, Ref, ShallowRef } from 'vue'
import type { KnowledgeBaseRow } from '@/api/admin'
import type { ChatMessageRow, Citation, ConversationRow, GenerationRun } from '@/api/chat'

/** 对话工作区页面模板使用的状态和业务操作契约。 */
export interface ChatPageState {
  knowledgeBases: Ref<KnowledgeBaseRow[]>
  knowledgeBaseId: ShallowRef<string>
  selectedKnowledgeBase: ComputedRef<KnowledgeBaseRow | null>
  conversations: Ref<ConversationRow[]>
  conversationId: ShallowRef<string>
  selectedConversation: ComputedRef<ConversationRow | null>
  messages: Ref<ChatMessageRow[]>
  currentRun: ShallowRef<GenerationRun | null>
  question: ShallowRef<string>
  loading: ShallowRef<boolean>
  loadError: ShallowRef<string>
  sending: ShallowRef<boolean>
  deletingConversationId: ShallowRef<string>
  canSend: ComputedRef<boolean>
  citationPanelOpen: ShallowRef<boolean>
  selectedCitations: Ref<Citation[]>
  selectConversation: (conversationId: string) => Promise<void>
  newConversation: () => Promise<ConversationRow | null>
  removeConversation: (conversationId: string) => Promise<void>
  sendQuestion: () => Promise<void>
  stopGeneration: () => Promise<void>
  retry: (message: ChatMessageRow) => Promise<void>
  resume: (message: ChatMessageRow) => Promise<void>
  showCitations: (citations: Citation[]) => void
  closeCitations: () => void
  feedback: (message: ChatMessageRow, rating: 'helpful' | 'not_helpful') => Promise<void>
  loadConversations: () => Promise<void>
}
