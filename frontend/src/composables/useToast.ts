/**
 * AppToast 的业务调用契约与注入入口。
 *
 * 页面逻辑只依赖这里暴露的动作，不直接操作 Reka UI 的渲染细节；
 * 根组件中的 AppToast 是唯一渲染宿主，保证所有成功、失败和信息反馈使用同一套视觉与无障碍行为。
 */
import type { InjectionKey } from 'vue'
import { inject } from 'vue'

export type ToastTone = 'success' | 'error' | 'info'

/** 单条 Toast 的业务内容；duration 为毫秒，省略时使用全局默认值。 */
export interface ToastOptions {
  title: string
  description?: string
  duration?: number
  tone?: ToastTone
}

/** 页面可调用的最小 Toast API，避免业务层依赖视图状态。 */
export interface ToastController {
  show: (options: ToastOptions) => void
  success: (title: string, description?: string) => void
  error: (title: string, description?: string) => void
  info: (title: string, description?: string) => void
}

export const toastKey: InjectionKey<ToastController> = Symbol('ragmanage-toast')

/** 测试或独立挂载业务组件时没有 Host 的安全降级实现。 */
const fallbackToast: ToastController = {
  show: () => undefined,
  success: () => undefined,
  error: () => undefined,
  info: () => undefined,
}

/** 获取根组件提供的 AppToast 控制器；未挂载宿主时保持业务操作可执行。 */
export function useAppToast(): ToastController {
  return inject(toastKey, fallbackToast)
}

/**
 * 兼容旧页面的调用名；它与 useAppToast 指向同一个注入控制器，避免业务迁移期间出现第二套 Toast 实现。
 */
export const useToast = useAppToast
