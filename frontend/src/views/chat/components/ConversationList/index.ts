/** 会话列表本地交互状态与显示格式化逻辑。 */
import type { ComputedRef, Ref } from 'vue'
import type { ConversationListProps } from './type'
import type { ConversationRow } from '@/api/chat'
import { computed, shallowRef } from 'vue'

/** 管理会话列表的删除确认、悬停状态及显示格式化，不触碰服务端数据。 */
export function useConversationList(
  props: ConversationListProps,
  emit: { (event: 'delete', conversationId: string): void },
): {
  pendingDelete: Ref<ConversationRow | null>
  hoveredConversationId: Ref<string | null>
  deleteDialogOpen: ComputedRef<boolean>
  formatDate: (value: string) => string
  requestDelete: (conversation: ConversationRow) => void
  confirmDelete: () => void
  handleConversationEnter: (conversationId: string) => void
  handleConversationLeave: (conversationId: string) => void
} {
  const pendingDelete = shallowRef<ConversationRow | null>(null)
  const hoveredConversationId = shallowRef<string | null>(null)
  const deleteDialogOpen = computed({
    get: () => Boolean(pendingDelete.value),
    set: (value: boolean) => {
      if (!value) pendingDelete.value = null
    },
  })

  function formatDate(value: string): string {
    return new Date(value).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  }
  function requestDelete(conversation: ConversationRow): void {
    if (!props.disabled) pendingDelete.value = conversation
  }
  function confirmDelete(): void {
    if (!pendingDelete.value) return
    emit('delete', pendingDelete.value.id)
    pendingDelete.value = null
  }
  function handleConversationEnter(conversationId: string): void {
    hoveredConversationId.value = conversationId
  }
  function handleConversationLeave(conversationId: string): void {
    if (hoveredConversationId.value === conversationId) hoveredConversationId.value = null
  }
  return {
    pendingDelete,
    hoveredConversationId,
    deleteDialogOpen,
    formatDate,
    requestDelete,
    confirmDelete,
    handleConversationEnter,
    handleConversationLeave,
  }
}
