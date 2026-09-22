import {
  DialogClose as RekaDialogClose,
  DialogContent as RekaDialogContent,
  DialogDescription as RekaDialogDescription,
  DialogOverlay as RekaDialogOverlay,
  DialogPortal as RekaDialogPortal,
  DialogRoot as RekaDialogRoot,
  DialogTitle as RekaDialogTitle,
  DialogTrigger as RekaDialogTrigger,
} from 'reka-ui'
import { defineComponent, h } from 'vue'

/**
 * shadcn-vue 风格 Dialog 原语：只负责把 Reka UI 的无障碍行为和官网常用的
 * Header、Footer、Content 组合方式统一导出；业务弹窗仍可通过 class 覆盖布局。
 */
export const Dialog = RekaDialogRoot
/** Reka UI 命名别名，便于兼容现有受控封装的 Root 语义。 */
export const DialogRoot = RekaDialogRoot
export const DialogTrigger = RekaDialogTrigger
export const DialogPortal = RekaDialogPortal
export const DialogClose = RekaDialogClose
export const DialogTitle = RekaDialogTitle
export const DialogDescription = RekaDialogDescription

/** 透传 Reka UI 属性和事件的通用原语包装，避免自定义组件吞掉 attrs。 */
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

/** Dialog 蒙层采用语义背景色，动画状态由 Reka UI data-state 提供。 */
export const DialogOverlay = forwardPrimitive(
  RekaDialogOverlay,
  'DialogOverlay',
  'fixed inset-0 bg-foreground/40 data-[state=open]:animate-in data-[state=closed]:animate-out',
)

/**
 * Dialog 内容默认遵循 shadcn-vue 的居中卡片；AppDialog 通过传入透明布局类复用
 * 焦点陷阱和 Portal，同时让业务卡片继续保留已有领域样式。
 */
export const DialogContent = forwardPrimitive(
  RekaDialogContent,
  'DialogContent',
  'fixed left-1/2 top-1/2 z-50 grid w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 gap-[16px] rounded-lg border border-border bg-card p-[24px] text-foreground shadow-lg focus:outline-none',
)

/** 官网示例中的标题区域，使用 gap 而不是隐式 margin 维持稳定节奏。 */
export const DialogHeader = defineComponent({
  name: 'DialogHeader',
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () =>
      h('div', { ...attrs, class: ['flex flex-col gap-[6px] text-left', attrs.class] }, slots)
  },
})

/** 官网示例中的操作区域；移动端默认堆叠，桌面端恢复右对齐横排。 */
export const DialogFooter = defineComponent({
  name: 'DialogFooter',
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
