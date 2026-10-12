/** 创建知识库弹窗逻辑：提供受控表单并向父页面发出提交/取消事件。 */
import type { KnowledgeBaseForm } from '../../type'
import type { CreateKnowledgeBaseDialogProps } from './type'
import { ref, watch } from 'vue'

/** 声明表单和事件契约，异步提交由父页面统一处理。 */
export function useCreateKnowledgeBaseDialog(props: CreateKnowledgeBaseDialogProps) {
  const draft = ref<KnowledgeBaseForm>({ ...props.form })

  // 弹窗每次打开都会收到重置后的表单对象，因此复制到本地草稿避免直接改写父页面状态。
  watch(
    () => props.form,
    (form) => {
      draft.value = { ...form }
    },
    { immediate: true },
  )

  function submit(emit: (event: 'submit', value: KnowledgeBaseForm) => void): void {
    emit('submit', { ...draft.value })
  }

  return { draft, submit }
}
