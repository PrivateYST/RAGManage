<!--
  破坏性操作确认框：统一封装 shadcn-vue 风格 AlertDialog 的遮罩、焦点和取消行为。
  业务页面只提供对象名称、后果说明和确认事件，不再自行实现 backdrop 或 confirm。
-->
<script setup lang="ts">
import {
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogRoot,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface Props {
  open: boolean
  title: string
  description: string
  contentClass?: string
  confirmLabel?: string
  busy?: boolean
  destructive?: boolean
  cancelLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  confirmLabel: '确认',
  contentClass: '',
  busy: false,
  destructive: true,
  cancelLabel: '取消',
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  cancel: []
  confirm: []
}>()

/** 取消只改变受控状态，不触发业务副作用。 */
function close(): void {
  if (!props.busy) {
    emit('update:open', false)
    emit('cancel')
  }
}

/** 确认按钮使用普通按钮保持异步请求期间弹窗可见并展示禁用态。 */
function confirm(): void {
  if (!props.busy) emit('confirm')
}

/** AlertDialog 的受控更新只接受用户发起的关闭动作，忙碌时维持当前状态。 */
function handleOpenChange(value: boolean): void {
  if (!value) close()
}
</script>

<template>
  <AlertDialogRoot :open="props.open" @update:open="handleOpenChange">
    <AlertDialogPortal>
      <AlertDialogOverlay class="fixed inset-0 z-40 bg-foreground/40" />
      <AlertDialogContent
        class="fixed left-1/2 top-1/2 z-50 w-[min(420px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-[22px] text-foreground shadow-[0_18px_48px_rgb(24_24_27_/_16%)] focus:outline-none"
        :class="props.contentClass"
      >
        <AlertDialogHeader>
          <AlertDialogTitle class="text-base font-semibold leading-[24px]">
            {{ title }}
          </AlertDialogTitle>
          <AlertDialogDescription class="text-[11px] leading-[18px] text-muted-foreground">
            {{ description }}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div v-if="$slots.body" class="mt-[14px]">
          <slot name="body" />
        </div>
        <slot v-if="$slots.footer" name="footer" />
        <AlertDialogFooter v-else class="mt-[8px]">
          <AlertDialogCancel
            class="inline-flex h-[36px] items-center justify-center rounded-md border border-border bg-background px-[13px] text-xs font-medium text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50"
            :disabled="busy"
          >
            {{ cancelLabel }}
          </AlertDialogCancel>
          <button
            type="button"
            class="inline-flex h-[36px] items-center justify-center rounded-md px-[13px] text-xs font-medium text-white transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50"
            :class="
              destructive
                ? 'bg-destructive hover:bg-destructive/90'
                : 'bg-primary hover:bg-primary/90'
            "
            :disabled="busy"
            @click="confirm"
          >
            {{ busy ? '处理中…' : confirmLabel }}
          </button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>
