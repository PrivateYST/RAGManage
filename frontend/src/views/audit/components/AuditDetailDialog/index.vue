<!-- 审计详情弹窗：只读展示事件元数据和完整变更摘要。 -->
<script setup lang="ts">
import type { AuditDetailDialogProps } from './type'
import { Braces, X } from '@/components'
import { auditActionLabel, auditSummaryJson, auditTargetLabel, formatAuditTime } from './index'
import './index.scss'

/** 详情事件由父页面传入，组件不在本地修改不可变审计数据。 */
defineProps<AuditDetailDialogProps>()
/** close 事件由遮罩和关闭按钮触发，交由父页面清理选择状态。 */
defineEmits<{ close: [] }>()
</script>

<template>
  <div class="dialog-backdrop audit-detail-backdrop" @click.self="$emit('close')">
    <section
      class="dialog-card audit-detail-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="audit-detail-title"
    >
      <header class="dialog-heading">
        <div>
          <p class="eyebrow">审计事件 #{{ item.id }}</p>
          <h2 id="audit-detail-title">
            {{ auditActionLabel(item.action) }}
          </h2>
        </div>
        <button
          class="dialog-close"
          type="button"
          aria-label="关闭审计详情"
          @click="$emit('close')"
        >
          <X :size="16" aria-hidden="true" />
        </button>
      </header>

      <dl class="audit-detail-grid">
        <div>
          <dt>发生时间</dt>
          <dd>{{ formatAuditTime(item.created_at) }}</dd>
        </div>
        <div>
          <dt>操作人</dt>
          <dd>
            {{ item.actor_name || '系统' }}<small>{{ item.actor_login || 'system' }}</small>
          </dd>
        </div>
        <div>
          <dt>所属范围</dt>
          <dd>{{ item.tenant_name || '平台级' }}</dd>
        </div>
        <div>
          <dt>目标对象</dt>
          <dd>{{ auditTargetLabel(item.target_type) }} · {{ item.target_id || '—' }}</dd>
        </div>
        <div class="wide">
          <dt>操作标识</dt>
          <dd>
            <code>{{ item.action }}</code>
          </dd>
        </div>
        <div class="wide">
          <dt>Request ID</dt>
          <dd>
            <code>{{ item.request_id || '未记录' }}</code>
          </dd>
        </div>
      </dl>

      <div class="audit-json-block">
        <div><Braces :size="15" aria-hidden="true" /><strong>变更摘要</strong></div>
        <pre>{{ auditSummaryJson(item) }}</pre>
      </div>
    </section>
  </div>
</template>
