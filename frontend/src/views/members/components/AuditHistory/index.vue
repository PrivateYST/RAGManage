<script setup lang="ts">
import type { AuditHistoryProps } from './type'
import { History } from '@/components'
import { actionLabel, summaryText } from './index'
import './index.scss'

defineProps<AuditHistoryProps>()
</script>

<template>
  <section class="content-card member-audit-card">
    <header>
      <div>
        <span><History :size="16" /></span>
        <div><strong>授权历史</strong><small>最近 100 条成员和知识库授权变更。</small></div>
      </div>
    </header>
    <div v-if="loading" class="member-state">
      <span class="loading-spinner" /><strong>正在加载授权历史…</strong>
    </div>
    <div v-else-if="items.length === 0" class="member-state">
      <History :size="24" /><strong>暂无授权变更记录</strong>
    </div>
    <ol v-else class="member-audit-list">
      <li v-for="item in items" :key="item.id">
        <span class="audit-dot" />
        <div>
          <div>
            <strong>{{ actionLabel(item.action) }}</strong
            ><time>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</time>
          </div>
          <p>
            {{ item.actor_name || '系统' }} 对
            {{ item.target_name || `用户 #${item.target_id}` }} 执行操作
          </p>
          <small>{{ summaryText(item.change_summary) }}</small>
        </div>
      </li>
    </ol>
  </section>
</template>
