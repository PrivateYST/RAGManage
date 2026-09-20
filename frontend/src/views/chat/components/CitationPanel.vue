<script setup lang="ts">
import type { Citation } from '@/api/chat'
import { ExternalLink, FileText, X } from '@/components'

defineProps<{ open: boolean; citations: Citation[] }>()
const emit = defineEmits<{ close: [] }>()

function locatorLabel(locator: Record<string, number>): string {
  if (locator.page !== undefined) return `第 ${locator.page} 页`
  if (locator.line_start !== undefined)
    return `第 ${locator.line_start}–${locator.line_end ?? locator.line_start} 行`
  if (locator.char_start !== undefined)
    return `字符 ${locator.char_start}–${locator.char_end ?? locator.char_start}`
  return '原文片段'
}
</script>

<template>
  <aside v-if="open" class="citation-panel" aria-label="回答引用">
    <header>
      <div><FileText :size="15" aria-hidden="true" /><strong>回答引用</strong></div>
      <button type="button" aria-label="关闭引用" @click="emit('close')">
        <X :size="15" />
      </button>
    </header>
    <div class="citation-list">
      <article v-for="citation in citations" :key="citation.evidence_no">
        <div class="citation-number">
          {{ citation.evidence_no }}
        </div>
        <div>
          <strong>{{ citation.document_title }}</strong>
          <span
            >V{{ citation.version_no }} · {{ citation.section_path.join(' / ') || '正文' }}</span
          >
          <p>{{ citation.content }}</p>
          <RouterLink :to="citation.source_path">
            {{ locatorLabel(citation.locator) }}<ExternalLink :size="11" aria-hidden="true" />
          </RouterLink>
        </div>
      </article>
    </div>
  </aside>
</template>
