import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogDescription,
  AlertDialogPortal,
  AlertDialogRoot,
  AlertDialogTitle,
  AlertDialogTrigger,
  AlertDialogContent as RekaAlertDialogContent,
  AlertDialogOverlay as RekaAlertDialogOverlay,
} from 'reka-ui'
import { defineComponent, h } from 'vue'

/**
 * shadcn-vue 风格 AlertDialog 原语：为破坏性操作提供强制决策、焦点回收和
 * 可访问语义；具体按钮文案与业务副作用由上层封装注入。
 */
export {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogDescription,
  AlertDialogPortal,
  AlertDialogRoot,
  AlertDialogTitle,
  AlertDialogTrigger,
}

function forwardPrimitive(component: unknown, name: string, defaultClass?: string) {
  return defineComponent({
    name,
    inheritAttrs: false,
    props: {
      /** 内部业务壳需要完全接管布局时使用，避免与默认卡片样式叠加。 */
      unstyled: { type: Boolean, default: false },
    },
    setup(props, { attrs, slots }) {
      return () =>
        h(
          component as never,
          {
            ...attrs,
            class: defaultClass && !props.unstyled ? [defaultClass, attrs.class] : attrs.class,
          },
          slots,
        )
    },
  })
}

/** AlertDialog 蒙层与普通 Dialog 保持同一套语义色和状态动画。 */
export const AlertDialogOverlay = forwardPrimitive(
  RekaAlertDialogOverlay,
  'AlertDialogOverlay',
  'fixed inset-0 bg-foreground/40 data-[state=open]:animate-in data-[state=closed]:animate-out',
)

/** AlertDialog 内容卡片，保留官网示例的紧凑标题、描述和 footer 组合空间。 */
export const AlertDialogContent = forwardPrimitive(
  RekaAlertDialogContent,
  'AlertDialogContent',
  'fixed left-1/2 top-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-[16px] rounded-lg border border-border bg-card p-[24px] text-foreground shadow-lg focus:outline-none',
)

/** AlertDialog 标题区域与 DialogHeader 保持相同的结构语义。 */
export const AlertDialogHeader = defineComponent({
  name: 'AlertDialogHeader',
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () =>
      h('div', { ...attrs, class: ['flex flex-col gap-[6px] text-left', attrs.class] }, slots)
  },
})

/** AlertDialog 操作区域在窄屏堆叠，避免确认按钮被挤压。 */
export const AlertDialogFooter = defineComponent({
  name: 'AlertDialogFooter',
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () =>
      h(
        'div',
        {
          ...attrs,
          class: ['flex flex-col-reverse gap-[8px] sm:flex-row sm:justify-end', attrs.class],
        },
        slots,
      )
  },
})
