import type { CreateSpaceForm } from './type'
/** 新建客户空间弹窗逻辑：管理表单状态并把提交结果交给页面处理。 */
import { ref } from 'vue'

/** 新窗口打开时重置表单，成功由父级回调关闭弹窗。 */
export function useCreateSpaceDialog() {
  const form = ref<CreateSpaceForm>({ code: '', name: '' })

  /** 清除上一次录入，避免空间编码或名称意外复用。 */
  function reset(): void {
    form.value = { code: '', name: '' }
  }

  return { form, reset }
}
