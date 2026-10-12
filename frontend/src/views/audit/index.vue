<!-- 操作日志业务页：只编排页面状态、筛选栏、事件表格和详情弹窗。 -->
<script setup lang="ts">
import { RefreshCw, Search } from '@/components'
import AuditDetailDialog from './components/AuditDetailDialog/index.vue'
import AuditFilters from './components/AuditFilters/index.vue'
import AuditTable from './components/AuditTable/index.vue'
import { useAuditLogs } from './index'
import './index.scss'

const {
  auth,
  items,
  filters,
  loading,
  errorMessage,
  loadingMore,
  nextCursor,
  selected,
  isPlatformAdmin,
  load,
  resetFilters,
} = useAuditLogs()
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

    <AuditFilters
      :scope="filters.scope"
      :action-prefix="filters.actionPrefix"
      :actor="filters.actor"
      :target-type="filters.targetType"
      :space-name="auth.activeSpace?.name || ''"
      :is-platform-admin="isPlatformAdmin"
      :loading="loading"
      @update:scope="filters.scope = $event"
      @update:action-prefix="filters.actionPrefix = $event"
      @update:actor="filters.actor = $event"
      @update:target-type="filters.targetType = $event"
      @submit="load(true)"
      @reset="resetFilters"
    />

    <div
      v-if="errorMessage"
      class="content-card mb-[12px] flex items-center justify-between gap-[12px]"
      role="alert"
    >
      <span class="text-xs text-destructive">{{ errorMessage }}</span>
      <button class="secondary-button" type="button" @click="load(true)">
        <Search :size="14" aria-hidden="true" />重新加载日志
      </button>
    </div>

    <AuditTable
      :items="items"
      :loading="loading"
      :loading-more="loadingMore"
      :next-cursor="nextCursor"
      :scope="filters.scope"
      @select="selected = $event"
      @load-more="load(false)"
    />
    <AuditDetailDialog v-if="selected" :item="selected" @close="selected = null" />
  </section>
</template>
