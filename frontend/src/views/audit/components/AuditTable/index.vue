<!-- 操作日志表格：复用 AppTable，负责只读事件展示及用户意图事件。 -->
<script setup lang="ts">
import type { AuditTableEmits, AuditTableProps } from './type'
import { AppTable, Eye, FileClock, ShieldCheck } from '@/components'
import { auditActionLabel, auditTargetLabel } from '../../enum'
import { auditColumns, auditSummaryText, formatAuditTableTime } from './index'
import './index.scss'

defineProps<AuditTableProps>()
const emit = defineEmits<AuditTableEmits>()
</script>

<template>
  <section class="content-card overflow-hidden p-0">
    <header
      class="flex min-h-[64px] items-center justify-between border-b border-border px-[16px] py-[10px]"
    >
      <div class="flex items-center gap-[10px]">
        <span class="grid size-[32px] place-items-center rounded-md bg-primary/10 text-primary"
          ><ShieldCheck :size="16" aria-hidden="true"
        /></span>
        <div>
          <strong class="block text-[13px] font-semibold">不可变审计事件</strong>
          <small class="mt-[2px] block text-[10px] text-muted-foreground"
            >当前已加载 {{ items.length }} 条</small
          >
        </div>
      </div>
      <span
        class="inline-flex min-h-[20px] items-center rounded-full bg-status-up-soft px-[8px] text-[10px] font-medium text-status-up"
        >{{ scope === 'space' ? '空间范围' : '平台范围' }}</span
      >
    </header>
    <div class="overflow-x-auto">
      <AppTable
        :rows="items"
        :columns="auditColumns"
        row-key="id"
        :loading="loading"
        class="w-full min-w-[1050px] text-left"
      >
        <template #cell-time="{ row: item }"
          ><time class="text-[10px] text-muted-foreground" :datetime="item.created_at">{{
            formatAuditTableTime(item.created_at)
          }}</time></template
        >
        <template #cell-actor="{ row: item }"
          ><strong class="block text-xs font-semibold text-foreground">{{
            item.actor_name || '系统'
          }}</strong
          ><small class="mt-[2px] block text-[9px] text-muted-foreground">{{
            item.actor_login || 'system'
          }}</small></template
        >
        <template #cell-action="{ row: item }"
          ><span
            class="inline-flex min-h-[20px] items-center rounded-full bg-primary/10 px-[8px] text-[10px] font-medium text-primary"
            >{{ auditActionLabel(item.action) }}</span
          ><code class="mt-[4px] block font-mono text-[9px]">{{ item.action }}</code></template
        >
        <template #cell-target="{ row: item }"
          ><strong class="block text-xs font-semibold text-foreground">{{
            auditTargetLabel(item.target_type)
          }}</strong
          ><small class="mt-[2px] block text-[9px]">#{{ item.target_id || '—' }}</small></template
        >
        <template #cell-summary="{ row: item }"
          ><p class="m-0 max-w-[360px] truncate text-[10px] leading-[1.55]">
            {{ auditSummaryText(item) }}
          </p></template
        >
        <template #cell-scope="{ row: item }">{{ item.tenant_name || '平台级' }}</template>
        <template #cell-details="{ row: item }"
          ><button class="table-action" type="button" @click="emit('select', item)">
            <Eye :size="13" aria-hidden="true" />详情
          </button></template
        >
        <template #empty
          ><div
            class="flex min-h-[180px] flex-col items-center justify-center gap-[4px] text-muted-foreground"
          >
            <FileClock :size="24" aria-hidden="true" /><strong>没有符合条件的日志</strong
            ><span>调整筛选条件后重新查询。</span>
          </div></template
        >
      </AppTable>
    </div>
    <footer
      v-if="items.length"
      class="flex min-h-[52px] items-center justify-between border-t border-border px-[16px] py-[8px] text-[10px] text-muted-foreground"
    >
      <span>日志按发生时间倒序排列</span>
      <button
        v-if="nextCursor"
        class="secondary-button"
        type="button"
        :disabled="loadingMore"
        @click="emit('loadMore')"
      >
        {{ loadingMore ? '加载中…' : '加载更多' }}
      </button>
      <span v-else>已加载全部结果</span>
    </footer>
  </section>
</template>
