<!-- 操作日志业务页：组合筛选、不可变事件表格和详情弹窗。 -->
<script setup lang="ts">
import type { AuditLogItem } from '@/api/audit'
import type { AppTableColumn } from '@/components'
import {
  AppTable,
  Eye,
  FileClock,
  Filter,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
} from '@/components'
import AuditDetailDialog from './components/AuditDetailDialog/index.vue'
import { auditActionLabel, auditActionOptions, auditTargetLabel, auditTargetOptions } from './enum'
import { useAuditLogs } from './index'

const {
  auth,
  items,
  filters,
  loading,
  loadingMore,
  nextCursor,
  selected,
  isPlatformAdmin,
  load,
  resetFilters,
} = useAuditLogs()

/** 将服务端时间转换为用户本地的 24 小时制展示。 */
function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

/** 生成表格中的安全摘要预览；完整 JSON 仅在详情弹窗展示。 */
function summaryText(item: AuditLogItem): string {
  const entries = Object.entries(item.change_summary)
  if (!entries.length) return '没有附加变更摘要'
  const text = entries
    .slice(0, 3)
    .map(([key, value]) => {
      const rendered = typeof value === 'object' ? JSON.stringify(value) : String(value)
      return `${key}: ${rendered}`
    })
    .join(' · ')
  return text.length > 120 ? `${text.slice(0, 117)}…` : text
}

const auditColumns: AppTableColumn<AuditLogItem>[] = [
  { key: 'time', title: '时间', cellClass: 'whitespace-nowrap px-[18px] py-[14px]' },
  { key: 'actor', title: '操作人', cellClass: 'px-[18px] py-[14px]' },
  { key: 'action', title: '操作', cellClass: 'px-[18px] py-[14px]' },
  { key: 'target', title: '目标', cellClass: 'px-[18px] py-[14px]' },
  { key: 'summary', title: '变更摘要', cellClass: 'px-[18px] py-[14px]' },
  { key: 'scope', title: '范围', cellClass: 'px-[18px] py-[14px]' },
  { key: 'details', title: '操作', cellClass: 'px-[18px] py-[14px]' },
]
</script>

<template>
  <section class="mx-auto w-full max-w-[1160px] pb-[28px]">
    <div class="page-intro">
      <div>
        <p class="eyebrow">系统管理</p>
        <h1>操作日志</h1>
        <p class="page-description">
          查询登录、授权、内容发布和配置变更，空间日志仅对显式授权的空间管理员开放。
        </p>
      </div>
      <button
        class="secondary-button"
        type="button"
        :disabled="loading || loadingMore"
        @click="load(true)"
      >
        <RefreshCw :class="{ 'animate-spin': loading }" :size="14" aria-hidden="true" />
        {{ loading ? '刷新中…' : '刷新日志' }}
      </button>
    </div>

    <form
      class="content-card mb-[14px] grid items-end gap-[12px] p-[16px] lg:grid-cols-[190px_180px_180px_minmax(180px,1fr)_auto]"
      @submit.prevent="load(true)"
    >
      <div class="flex items-center gap-[8px] lg:hidden">
        <span class="grid size-[30px] place-items-center rounded-md bg-primary/10 text-primary"
          ><Filter :size="15" aria-hidden="true"
        /></span>
        <div>
          <strong class="block text-xs">筛选日志</strong
          ><small class="mt-[2px] block text-[9px] text-muted-foreground"
            >筛选条件只作用于当前日志范围</small
          >
        </div>
      </div>
      <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
        <span>日志范围</span
        ><select
          v-model="filters.scope"
          class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        >
          <option value="space">当前空间 · {{ auth.activeSpace?.name || '未选择' }}</option>
          <option v-if="isPlatformAdmin" value="platform">平台级配置</option>
        </select>
      </label>
      <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
        <span>操作类型</span
        ><select
          v-model="filters.actionPrefix"
          class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        >
          <option v-for="option in auditActionOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
        <span>目标对象</span
        ><select
          v-model="filters.targetType"
          class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        >
          <option v-for="option in auditTargetOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
        <span>操作人</span>
        <div class="relative">
          <Search
            class="absolute left-[10px] top-[10px] text-muted-foreground"
            :size="14"
            aria-hidden="true"
          /><input
            v-model.trim="filters.actor"
            class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] pl-[32px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
            maxlength="100"
            placeholder="姓名或登录名"
          />
        </div>
      </label>
      <div class="flex gap-[8px] max-lg:justify-end max-sm:col-span-1 max-sm:[&>button]:flex-1">
        <button class="secondary-button" type="button" :disabled="loading" @click="resetFilters">
          <RotateCcw :size="14" aria-hidden="true" />重置
        </button>
        <button class="primary-button" type="submit" :disabled="loading">
          <Search :size="14" aria-hidden="true" />查询
        </button>
      </div>
    </form>

    <section class="content-card overflow-hidden p-0">
      <header
        class="flex min-h-[64px] items-center justify-between border-b border-border px-[16px] py-[10px]"
      >
        <div class="flex items-center gap-[10px]">
          <span class="grid size-[32px] place-items-center rounded-md bg-primary/10 text-primary"
            ><ShieldCheck :size="16" aria-hidden="true"
          /></span>
          <div>
            <strong class="block text-[13px] font-semibold">不可变审计事件</strong
            ><small class="mt-[2px] block text-[10px] text-muted-foreground"
              >当前已加载 {{ items.length }} 条</small
            >
          </div>
        </div>
        <span
          class="inline-flex min-h-[20px] items-center rounded-full bg-status-up-soft px-[8px] text-[10px] font-medium text-status-up"
          >{{ filters.scope === 'space' ? '空间范围' : '平台范围' }}</span
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
          <template #cell-time="{ row: item }">
            <time class="text-[10px] text-muted-foreground" :datetime="item.created_at">{{
              formatTime(item.created_at)
            }}</time>
          </template>
          <template #cell-actor="{ row: item }">
            <strong class="block text-xs font-semibold text-foreground">{{
              item.actor_name || '系统'
            }}</strong>
            <small class="mt-[2px] block text-[9px] text-muted-foreground">{{
              item.actor_login || 'system'
            }}</small>
          </template>
          <template #cell-action="{ row: item }">
            <span
              class="inline-flex min-h-[20px] items-center rounded-full bg-primary/10 px-[8px] text-[10px] font-medium text-primary"
              >{{ auditActionLabel(item.action) }}</span
            >
            <code class="mt-[4px] block font-mono text-[9px]">{{ item.action }}</code>
          </template>
          <template #cell-target="{ row: item }">
            <strong class="block text-xs font-semibold text-foreground">{{
              auditTargetLabel(item.target_type)
            }}</strong>
            <small class="mt-[2px] block text-[9px]">#{{ item.target_id || '—' }}</small>
          </template>
          <template #cell-summary="{ row: item }">
            <p class="m-0 max-w-[360px] truncate text-[10px] leading-[1.55]">
              {{ summaryText(item) }}
            </p>
          </template>
          <template #cell-scope="{ row: item }">{{ item.tenant_name || '平台级' }}</template>
          <template #cell-details="{ row: item }">
            <button class="table-action" type="button" @click="selected = item">
              <Eye :size="13" aria-hidden="true" />详情
            </button>
          </template>
          <template #empty>
            <div
              class="flex min-h-[180px] flex-col items-center justify-center gap-[4px] text-muted-foreground"
            >
              <FileClock :size="24" aria-hidden="true" /><strong>没有符合条件的日志</strong>
              <span>调整筛选条件后重新查询。</span>
            </div>
          </template>
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
          @click="load(false)"
        >
          {{ loadingMore ? '加载中…' : '加载更多' }}
        </button>
        <span v-else>已加载全部结果</span>
      </footer>
    </section>

    <AuditDetailDialog v-if="selected" :item="selected" @close="selected = null" />
  </section>
</template>
