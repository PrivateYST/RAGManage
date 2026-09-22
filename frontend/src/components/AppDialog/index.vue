<!--
  应用级业务弹窗壳：用 shadcn-vue 风格 Dialog 原语统一遮罩、Portal、焦点陷阱和 Escape 关闭。
  业务弹窗继续拥有自己的内容和领域样式，但不再重复实现 backdrop 行为。
-->
<script setup lang="ts">
import {
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
} from '@/components/ui/dialog'

interface Props {
  open: boolean
  title: string
  description?: string
  contentClass?: string
  /** 关闭时是否允许遮罩点击或 Escape；忙碌中的业务弹窗可关闭此能力。 */
  dismissible?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  description: '',
  contentClass: '',
  dismissible: true,
})
const emit = defineEmits<{
  'update:open': [value: boolean]
  close: []
}>()

/** 受控状态变更统一回传父组件，确保所有关闭入口走同一条业务清理链路。 */
function handleOpenChange(value: boolean): void {
  emit('update:open', value)
  if (!value) emit('close')
}

/** 非可关闭模式下阻止 Reka UI 的 Escape 关闭事件。 */
function handleEscapeKeyDown(event: Event): void {
  if (!props.dismissible) event.preventDefault()
}

/** 非可关闭模式下阻止遮罩或外部交互触发关闭。 */
function handleInteractOutside(event: Event): void {
  // 交互判定和 Portal/焦点陷阱交给 Reka UI；这里只处理业务要求的不可关闭状态。
  if (!props.dismissible) event.preventDefault()
}
</script>

<template>
  <DialogRoot :open="props.open" @update:open="handleOpenChange">
    <DialogPortal>
      <DialogOverlay class="pointer-events-auto fixed inset-0 z-40 bg-foreground/40" />
      <!--
        业务内容负责自己的卡片边框、宽度和阴影；壳层只提供定位与滚动，
        避免 Reka Dialog 和页面卡片叠成双层白色弹框。
      -->
      <DialogContent
        unstyled
        class="pointer-events-auto fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100vh-2.5rem)] w-[min(680px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 items-start justify-center overflow-y-auto bg-transparent p-0 text-foreground shadow-none focus:outline-none"
        :class="contentClass"
        :disable-outside-pointer-events="!props.dismissible"
        @escape-key-down="handleEscapeKeyDown"
        @interact-outside="handleInteractOutside"
      >
        <DialogHeader class="sr-only">
          <DialogTitle>{{ title }}</DialogTitle>
          <DialogDescription>{{ description || '业务操作弹窗' }}</DialogDescription>
        </DialogHeader>
        <slot />
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
