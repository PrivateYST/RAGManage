<!-- 操作日志业务页：组合筛选、不可变事件表格和详情弹窗。 -->
<script setup lang="ts">
import type { AuditLogItem } from '@/api/audit'
import { Eye, FileClock, Filter, RefreshCw, RotateCcw, Search, ShieldCheck } from '@/components'
import AuditDetailDialog from './components/AuditDetailDialog/index.vue'
import { auditActionLabel, auditActionOptions, auditTargetLabel, auditTargetOptions } from './enum'
import { useAuditLogs } from './index'
import './index.scss'

const {
  auth,
  items,
  filters,
  loading,
  loadingMore,
  error,
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
  if (!entries.length)
    return '没有附加变更摘要'
  const text = entries
    .slice(0, 3)
    .map(([key, value]) => {
      const rendered = typeof value === 'object' ? JSON.stringify(value) : String(value)
      return `${key}: ${rendered}`
    })
    .join(' · ')
  return text.length > 120 ? `${text.slice(0, 117)}…` : text
}
</script>

<template>
  <section class="page-section audit-page">
    <div class="page-intro">
      <div>
        <p class="eyebrow">
          系统管理
        </p>
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
        <RefreshCw :class="{ 'is-spinning': loading }" :size="14" aria-hidden="true" />
        {{ loading ? '刷新中…' : '刷新日志' }}
      </button>
    </div>

    <div v-if="error" class="error-banner" role="alert">
      {{ error }}
    </div>

    <form class="content-card audit-filter-card" @submit.prevent="load(true)">
      <div class="audit-filter-heading">
        <span><Filter :size="15" aria-hidden="true" /></span>
        <div><strong>筛选日志</strong><small>筛选条件只作用于当前日志范围</small></div>
      </div>
      <label>
        <span>日志范围</span>
        <select v-model="filters.scope">
          <option value="space">当前空间 · {{ auth.activeSpace?.name || '未选择' }}</option>
          <option v-if="isPlatformAdmin" value="platform">平台级配置</option>
        </select>
      </label>
      <label>
        <span>操作类型</span>
        <select v-model="filters.actionPrefix">
          <option v-for="option in auditActionOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label>
        <span>目标对象</span>
        <select v-model="filters.targetType">
          <option v-for="option in auditTargetOptions" :key="option.value" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <label class="audit-actor-filter">
        <span>操作人</span>
        <div>
          <Search :size="14" aria-hidden="true" /><input
            v-model.trim="filters.actor"
            maxlength="100"
            placeholder="姓名或登录名"
          >
        </div>
      </label>
      <div class="audit-filter-actions">
        <button class="secondary-button" type="button" :disabled="loading" @click="resetFilters">
          <RotateCcw :size="14" aria-hidden="true" />重置
        </button>
        <button class="primary-button" type="submit" :disabled="loading">
          <Search :size="14" aria-hidden="true" />查询
        </button>
      </div>
    </form>

    <section class="content-card audit-table-card">
      <header>
        <div>
          <span><ShieldCheck :size="16" aria-hidden="true" /></span>
          <div>
            <strong>不可变审计事件</strong><small>当前已加载 {{ items.length }} 条</small>
          </div>
        </div>
        <span class="status-pill ready">{{
          filters.scope === 'space' ? '空间范围' : '平台范围'
        }}</span>
      </header>

      <div v-if="loading" class="audit-state">
        <span class="loading-spinner" /><strong>正在加载操作日志…</strong>
      </div>
      <div v-else-if="!items.length" class="audit-state empty">
        <FileClock :size="24" aria-hidden="true" /><strong>没有符合条件的日志</strong><span>调整筛选条件后重新查询。</span>
      </div>
      <div v-else class="audit-table-wrap">
        <table>
          <thead>
            <tr>
              <th>时间</th>
              <th>操作人</th>
              <th>操作</th>
              <th>目标</th>
              <th>变更摘要</th>
              <th>范围</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in items" :key="item.id">
              <td>
                <time :datetime="item.created_at">{{ formatTime(item.created_at) }}</time>
              </td>
              <td>
                <strong>{{ item.actor_name || '系统' }}</strong><small>{{ item.actor_login || 'system' }}</small>
              </td>
              <td>
                <span class="audit-action-badge">{{ auditActionLabel(item.action) }}</span><code>{{ item.action }}</code>
              </td>
              <td>
                <strong>{{ auditTargetLabel(item.target_type) }}</strong><small>#{{ item.target_id || '—' }}</small>
              </td>
              <td>
                <p>{{ summaryText(item) }}</p>
              </td>
              <td>{{ item.tenant_name || '平台级' }}</td>
              <td>
                <button class="table-action" type="button" @click="selected = item">
                  <Eye :size="13" aria-hidden="true" />详情
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer v-if="items.length" class="audit-table-footer">
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
