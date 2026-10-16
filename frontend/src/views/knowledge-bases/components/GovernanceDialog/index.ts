import type { KnowledgeBaseForm } from '../../type'
/** 治理表单使用局部副本，取消不会直接改变父页面内容。 */
import type { GovernanceDialogProps } from './type'
import { reactive, watch } from 'vue'

/** 父页面切换知识库时同步草稿，字段编辑保留在局部。 */
export function useGovernanceDialog(props: GovernanceDialogProps) {
  const draft = reactive<KnowledgeBaseForm>({ ...props.form })
  watch(
    () => props.form,
    (value) => Object.assign(draft, value),
    { deep: true },
  )
  return { draft }
}
