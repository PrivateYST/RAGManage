/**
 * AppToast 的状态与注入逻辑；视图只负责把队列映射为 Reka UI Toast 原语。
 */
import type { ToastRecord } from './type'
import type { ToastController, ToastOptions, ToastTone } from '@/composables/useToast'
import { provide, shallowRef } from 'vue'
import { toastKey } from '@/composables/useToast'

let nextId = 0

/**
 * 提供应用级 Toast 控制器，并以数组替换方式维护 shallowRef，确保新增和关闭都能触发渲染。
 */
export function useAppToastHost() {
  const records = shallowRef<ToastRecord[]>([])

  function dismiss(id: number): void {
    records.value = records.value.filter((record) => record.id !== id)
  }

  function show(options: ToastOptions): void {
    const record: ToastRecord = {
      ...options,
      tone: options.tone ?? 'info',
      id: ++nextId,
    }
    records.value = [...records.value, record]
  }

  const controller: ToastController = {
    show,
    success: (title, description) => show({ title, description, tone: 'success' }),
    error: (title, description) => show({ title, description, tone: 'error' }),
    info: (title, description) => show({ title, description, tone: 'info' }),
  }

  provide(toastKey, controller)

  function toneClasses(tone: ToastTone): string {
    if (tone === 'success') return 'app-toast--success'
    if (tone === 'error') return 'app-toast--error'
    return 'app-toast--info'
  }

  return { records, dismiss, toneClasses }
}
