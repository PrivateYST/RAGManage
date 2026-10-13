import type { CreateSpaceForm } from './type'
/** 新建客户空间弹窗逻辑：管理表单状态并把提交结果交给页面处理。 */
import { ref } from 'vue'

/** 新窗口打开时重置表单，成功由父级回调关闭弹窗。 */
export function useCreateSpaceDialog() {
  const form = ref<CreateSpaceForm>({ code: '', name: '' })

  /** 编码在保存前统一转小写，避免用户输入 hospitalA 时触发服务端 slug 校验失败。 */
  function normalizeCode(value: string): string {
    return value.toLowerCase()
  }

  /** 直接同步输入框 DOM，避免 Vue 更新顺序让提交状态短暂保留大写编码。 */
  function handleCodeInput(event: Event): void {
    const input = event.currentTarget
    if (!(input instanceof HTMLInputElement)) return
    const normalized = normalizeCode(input.value)
    input.value = normalized
    form.value.code = normalized
  }

  /** 清除上一次录入，避免空间编码或名称意外复用。 */
  function reset(): void {
    form.value = { code: '', name: '' }
  }

  return { form, reset, normalizeCode, handleCodeInput }
}
