<!-- 用户详情弹窗：独立展示账号资料、空间授权和授权历史。 -->
<script setup lang="ts">
import type { UserDetailDialogProps } from './type'
import { AppDialog } from '@/components'
import { useUserDetailDialog } from './index'

const props = defineProps<UserDetailDialogProps>()
const emit = defineEmits<{ close: [] }>()
const { detail, loading } = useUserDetailDialog(props)
</script>

<template>
  <AppDialog
    :open="open"
    :title="detail ? `${detail.user.display_name} · 用户详情` : '用户详情'"
    content-class="w-[min(720px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <!-- AppDialog 提供透明定位壳，卡片负责详情弹窗的可读背景和内容间距。 -->
    <div
      v-if="loading"
      class="dialog-card flex w-full max-w-[720px] flex-col items-center gap-[12px] py-[32px]"
      role="status"
    >
      <span class="loading-spinner" />
      <p>正在读取授权历史…</p>
    </div>
    <div v-else-if="detail" class="dialog-card grid w-full max-w-[720px] gap-[20px]">
      <section>
        <p class="eyebrow">账号资料</p>
        <p class="text-sm">
          {{ detail.user.login }} · {{ detail.user.status === 'active' ? '正常' : '停用' }}
        </p>
      </section>
      <section>
        <p class="eyebrow">当前空间授权</p>
        <div v-if="detail.memberships.length" class="grid gap-[8px]">
          <div
            v-for="membership in detail.memberships"
            :key="`${membership.tenant_id}-${membership.role_code}`"
            class="rounded-md border border-border px-[12px] py-[8px] text-sm"
          >
            {{ membership.tenant_name }}（{{ membership.tenant_code }}） ·
            {{ membership.role_code }} · {{ membership.status }}
          </div>
        </div>
        <p v-else class="text-sm text-muted-foreground">暂无空间授权</p>
      </section>
      <section>
        <p class="eyebrow">授权历史</p>
        <div v-if="detail.history.length" class="grid gap-[8px]">
          <div
            v-for="event in detail.history"
            :key="event.id"
            class="rounded-md border border-border px-[12px] py-[8px] text-sm"
          >
            <strong>{{ event.action }}</strong>
            <span class="ml-[8px] text-muted-foreground">
              {{ new Date(event.created_at).toLocaleString('zh-CN') }}
            </span>
          </div>
        </div>
        <p v-else class="text-sm text-muted-foreground">暂无授权变更记录</p>
      </section>
    </div>
  </AppDialog>
</template>
