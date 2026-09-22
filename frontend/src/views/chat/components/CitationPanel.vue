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
  <aside
    v-if="open"
    class="flex min-w-0 flex-col border-l border-border bg-secondary max-[780px]:absolute max-[780px]:right-0 max-[780px]:z-10 max-[780px]:h-full max-[780px]:w-[min(320px,90%)]"
    aria-label="回答引用"
  >
    <header
      class="flex min-h-[48px] shrink-0 items-center justify-between border-b border-border px-[14px]"
    >
      <div class="flex items-center gap-[6px] text-muted-foreground">
        <FileText :size="15" aria-hidden="true" /><strong class="text-[11px]">回答引用</strong>
      </div>
      <button
        class="grid size-[26px] place-items-center rounded-md border-0 bg-transparent text-muted-foreground hover:bg-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        type="button"
        aria-label="关闭引用"
        @click="emit('close')"
      >
        <X :size="15" />
      </button>
    </header>
    <div class="min-h-0 flex-1 overflow-y-auto p-[8px]">
      <article
        v-for="citation in citations"
        :key="citation.evidence_no"
        class="grid grid-cols-[22px_minmax(0,1fr)] gap-[8px] rounded-md border border-border bg-card p-[10px]"
      >
        <div
          class="grid size-[22px] place-items-center rounded-md bg-primary/10 text-[10px] font-bold text-primary"
        >
          {{ citation.evidence_no }}
        </div>
        <div>
          <strong class="block truncate text-[10px] text-foreground">{{
            citation.document_title
          }}</strong>
          <span class="mt-[2px] block truncate text-[8px] text-muted-foreground"
            >V{{ citation.version_no }} · {{ citation.section_path.join(' / ') || '正文' }}</span
          >
          <p class="my-[6px] line-clamp-4 text-[9px] leading-[1.55] text-muted-foreground">
            {{ citation.content }}
          </p>
          <RouterLink
            class="inline-flex items-center gap-[4px] text-[9px] text-primary"
            :to="citation.source_path"
          >
            {{ locatorLabel(citation.locator) }}<ExternalLink :size="11" aria-hidden="true" />
          </RouterLink>
        </div>
      </article>
    </div>
  </aside>
</template>
