/**
 * AppToast 的渲染记录；在业务 ToastOptions 上补充宿主所需的稳定 id。
 */
import type { ToastOptions, ToastTone } from '@/composables/useToast'

export interface ToastRecord extends ToastOptions {
  id: number
  tone: ToastTone
}
