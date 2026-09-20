import type { CreateBuildDialogActions, CreateBuildDialogProps } from './type'
import { computed, shallowRef, watch } from 'vue'

export function useCreateBuildDialog(
  props: CreateBuildDialogProps,
  actions: CreateBuildDialogActions,
) {
  const targetKnowledgeBaseId = shallowRef('')

  const selectedKnowledgeBase = computed(
    () => props.knowledgeBases.find(item => item.id === targetKnowledgeBaseId.value) ?? null,
  )
  const canConfirm = computed(() => Boolean(selectedKnowledgeBase.value) && !props.creating)

  watch(
    [
      () => props.open,
      () => props.initialKnowledgeBaseId,
      () => props.knowledgeBases.map(item => item.id).join(','),
    ],
    ([open]) => {
      if (!open)
        return
      const initialExists = props.knowledgeBases.some(
        item => item.id === props.initialKnowledgeBaseId,
      )
      targetKnowledgeBaseId.value = initialExists
        ? props.initialKnowledgeBaseId
        : (props.knowledgeBases[0]?.id ?? '')
    },
    { immediate: true },
  )

  function handleClose(): void {
    if (!props.creating)
      actions.close()
  }

  function handleConfirm(): void {
    if (canConfirm.value)
      actions.confirm(targetKnowledgeBaseId.value)
  }

  return {
    targetKnowledgeBaseId,
    selectedKnowledgeBase,
    canConfirm,
    handleClose,
    handleConfirm,
  }
}
