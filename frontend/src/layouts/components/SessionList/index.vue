<!--
  登录会话纯展示列表：只显示服务端允许公开的时间与当前标识，不推断设备或 IP。
  撤销动作通过 typed emit 上交给管理弹窗，避免列表直接承担请求副作用。
-->
<script setup lang="ts">
import type { SessionListEmits, SessionListProps } from './type'
import { Clock3, LogOut, ShieldCheck } from '@/components'
import { formatSessionTimestamp } from './index'

const props = defineProps<SessionListProps>()
const emit = defineEmits<SessionListEmits>()
</script>

<template>
  <div class="session-list" aria-live="polite">
    <div v-if="props.loading && props.items.length === 0" class="session-state">
      <span class="loading-spinner" aria-hidden="true" />
      <span>正在加载会话…</span>
    </div>
    <div v-else-if="props.items.length === 0" class="session-state">
      <ShieldCheck :size="20" :aria-hidden="true" />
      <strong>没有其他有效会话</strong>
    </div>
    <ul v-else class="session-list-items">
      <li v-for="session in props.items" :key="session.id" class="session-list-item">
        <div class="session-list-item-main">
          <div class="session-list-title">
            <strong>会话 #{{ session.id }}</strong>
            <span
              v-if="session.is_current"
              class="rounded-full bg-primary/10 px-[8px] py-[3px] text-[10px] font-medium text-primary"
            >
              当前会话
            </span>
          </div>
          <div class="session-list-meta">
            <span
              ><Clock3 :size="13" :aria-hidden="true" />最近活动
              {{ formatSessionTimestamp(session.last_seen_at) }}</span
            >
            <span>登录于 {{ formatSessionTimestamp(session.created_at) }}</span>
            <span>到期于 {{ formatSessionTimestamp(session.expires_at) }}</span>
          </div>
        </div>
        <button
          class="session-list-item-action"
          type="button"
          :disabled="Boolean(props.busyId)"
          :aria-label="`${session.is_current ? '退出当前会话' : '下线会话'} ${session.id}`"
          @click="emit('revoke', session)"
        >
          <LogOut :size="14" :aria-hidden="true" />
          {{ session.is_current ? '退出当前设备' : '下线' }}
        </button>
      </li>
    </ul>
  </div>
</template>

<style src="./index.scss" scoped lang="scss"></style>
