<!--
  全局 Toast 宿主：将业务层的轻量通知记录映射为 Reka UI 原语，
  统一处理可访问性、自动关闭、暂停计时、键盘焦点和滑动关闭。
-->
<script setup lang="ts">
import {
  ToastClose,
  ToastDescription,
  ToastProvider,
  ToastRoot,
  ToastTitle,
  ToastViewport,
} from 'reka-ui'
import { X } from '@/components/icons'
import { useAppToastHost } from './index'
import './index.scss'

const { records, dismiss, toneClasses } = useAppToastHost()

/** Reka UI 在自动关闭、Escape、关闭按钮和滑动结束时都会回传 open 状态。 */
function handleOpenChange(id: number, open: boolean): void {
  if (!open) dismiss(id)
}
</script>

<template>
  <ToastProvider label="系统通知" :duration="4500" swipe-direction="right">
    <slot />
    <ToastViewport class="app-toast-viewport">
      <ToastRoot
        v-for="record in records"
        :key="record.id"
        :duration="record.duration"
        class="app-toast"
        :class="toneClasses(record.tone)"
        type="foreground"
        @update:open="handleOpenChange(record.id, $event)"
      >
        <div class="app-toast__content">
          <ToastTitle class="app-toast__title">
            {{ record.title }}
          </ToastTitle>
          <ToastDescription v-if="record.description" class="app-toast__description">
            {{ record.description }}
          </ToastDescription>
        </div>
        <ToastClose class="app-toast__close" aria-label="关闭通知">
          <X :size="15" aria-hidden="true" />
        </ToastClose>
      </ToastRoot>
    </ToastViewport>
  </ToastProvider>
</template>
