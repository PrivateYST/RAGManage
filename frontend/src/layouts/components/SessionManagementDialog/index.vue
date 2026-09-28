<!--
  登录会话管理弹窗：负责展示异步状态和危险操作确认，列表组件仅呈现数据并上抛意图。
  当前会话一旦被服务端撤销，即通知 AppShell 清除本地认证上下文并返回登录页。
-->
<script setup lang="ts">
import type { SessionManagementDialogEmits, SessionManagementDialogProps } from './type'
import { AppConfirmDialog, AppDialog, RefreshCw, ShieldCheck, X } from '@/components'
import SessionList from '../SessionList/index.vue'
import { useSessionManagementDialog } from './index'

const props = defineProps<SessionManagementDialogProps>()
const emit = defineEmits<SessionManagementDialogEmits>()
const {
  items,
  loading,
  loadError,
  busyId,
  pendingRevoke,
  load,
  requestRevoke,
  cancelRevoke,
  confirmRevoke,
} = useSessionManagementDialog(props, emit)

function close(): void {
  if (!busyId.value) emit('close')
}
</script>

<template>
  <AppDialog
    :open="props.open"
    title="登录会话管理"
    description="查看当前账号的有效登录会话并主动下线不再使用的会话。"
    content-class="w-[min(620px,calc(100vw-2rem))]"
    :dismissible="!busyId"
    @close="close"
  >
    <section
      class="session-dialog overflow-hidden rounded-lg border border-border bg-card shadow-[0_18px_48px_rgb(24_24_27_/_16%)]"
    >
      <header class="flex items-start justify-between gap-4 border-b border-border p-[20px]">
        <div class="flex items-start gap-[12px]">
          <span
            class="grid size-[34px] shrink-0 place-items-center rounded-md bg-primary/10 text-primary"
          >
            <ShieldCheck :size="18" :aria-hidden="true" />
          </span>
          <div>
            <h2 class="m-0 text-base font-semibold text-foreground">登录会话</h2>
            <p class="mb-0 mt-[5px] text-[11px] leading-[1.55] text-muted-foreground">
              仅显示当前账号的有效会话。下线后，该会话将无法继续访问。
            </p>
          </div>
        </div>
        <button
          class="grid size-[30px] shrink-0 place-items-center rounded-md border-0 bg-transparent text-muted-foreground hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          type="button"
          aria-label="关闭会话管理"
          :disabled="Boolean(busyId)"
          @click="close"
        >
          <X :size="17" :aria-hidden="true" />
        </button>
      </header>

      <div class="px-[20px] pb-[18px]">
        <div class="flex items-center justify-between gap-3 py-[12px]">
          <strong class="text-xs font-semibold text-foreground">有效会话</strong>
          <button
            class="inline-flex h-[30px] items-center gap-[6px] rounded-md border border-border bg-background px-[9px] text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            type="button"
            :disabled="loading"
            @click="load"
          >
            <RefreshCw :size="13" :class="loading ? 'animate-spin' : ''" :aria-hidden="true" />
            刷新
          </button>
        </div>
        <div v-if="loadError" class="session-error" role="alert">
          <span>{{ loadError }}</span>
          <button
            class="text-xs font-medium underline underline-offset-2"
            type="button"
            @click="load"
          >
            重试
          </button>
        </div>
        <SessionList :items="items" :loading="loading" :busy-id="busyId" @revoke="requestRevoke" />
      </div>
    </section>
  </AppDialog>

  <AppConfirmDialog
    :open="Boolean(pendingRevoke)"
    :title="pendingRevoke ? `确认下线会话 #${pendingRevoke.id}？` : '确认下线会话'"
    :description="
      pendingRevoke?.is_current
        ? '下线后当前浏览器会立即退出登录。'
        : '下线后该会话将立即失效，且需要重新登录才能恢复访问。'
    "
    confirm-label="确认下线"
    :busy="Boolean(pendingRevoke && busyId === pendingRevoke.id)"
    @update:open="(open) => !open && cancelRevoke()"
    @confirm="confirmRevoke"
  />
</template>

<style src="./index.scss" scoped lang="scss"></style>
