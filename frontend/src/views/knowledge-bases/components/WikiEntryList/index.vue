<!-- 词条列表：可见的来源、负责人、版本与单条快捷状态操作。 -->
<script setup lang="ts">
import type { WikiEntryListProps } from './type'
import type { WikiEntry, WikiStatus } from '@/api/wiki'
import { statusLabels } from './index'
import './index.scss'
defineProps<WikiEntryListProps>()
const emit = defineEmits<{
  edit: [entry: WikiEntry]
  transition: [entry: WikiEntry, status: WikiStatus]
  history: [entry: WikiEntry]
}>()
</script>
<template>
  <section class="grid gap-[12px]" aria-label="知识词条列表">
    <article
      v-for="entry in entries"
      :key="entry.id"
      class="rounded-lg border border-border bg-card p-[20px]"
    >
      <div class="flex flex-wrap items-start justify-between gap-[12px]">
        <div class="flex min-w-0 flex-wrap items-center gap-[8px]">
          <strong>{{ entry.term }}</strong>
          <span class="status-pill" :class="entry.status === 'published' ? 'ready' : ''">
            {{ statusLabels[entry.status] }}
          </span>
          <span class="text-xs text-muted-foreground">v{{ entry.version_no }}</span>
        </div>
        <div v-if="canManage" class="flex shrink-0 flex-wrap gap-[8px]">
          <button
            v-if="entry.status === 'draft' || entry.status === 'review'"
            class="primary-button"
            :disabled="busy"
            @click="emit('transition', entry, 'published')"
          >
            审核并发布
          </button>
          <button
            v-if="entry.status === 'review'"
            class="secondary-button"
            :disabled="busy"
            @click="emit('transition', entry, 'draft')"
          >
            退回草稿
          </button>
          <button
            v-if="entry.status === 'published'"
            class="secondary-button"
            :disabled="busy"
            @click="emit('transition', entry, 'retired')"
          >
            停用
          </button>
          <button
            v-if="entry.status === 'retired'"
            class="secondary-button"
            :disabled="busy"
            @click="emit('transition', entry, 'published')"
          >
            启用
          </button>
        </div>
      </div>
      <p class="my-[12px] whitespace-pre-wrap text-sm leading-relaxed">{{ entry.definition }}</p>
      <p class="text-xs text-muted-foreground">
        别名：{{ entry.aliases.join('、') || '无' }} · 负责人
        {{ entry.owner_user_id || '未指定' }} · {{ entry.valid_from || '不限起始' }} 至
        {{ entry.valid_until || '不限截止' }}
      </p>
      <div class="mt-[12px] grid gap-[6px] text-xs">
        <RouterLink
          v-for="source in entry.sources"
          :key="source.chunk_id"
          :to="{
            path: '/documents',
            query: {
              knowledge_base_id: entry.knowledge_base_id,
              document_id: source.document_id,
              version_id: source.document_version_id,
              chunk_id: source.chunk_id,
            },
          }"
          class="text-primary"
          >来源：{{ source.document_title || '原文已失效' }} · v{{ source.version_no }} ·
          {{ source.locator?.page ? `第 ${source.locator.page} 页` : '原文定位' }}
          {{ source.note }}</RouterLink
        >
      </div>
      <div
        v-if="canManage"
        class="mt-[16px] flex flex-wrap gap-[8px] border-t border-border pt-[12px]"
      >
        <button class="secondary-button" :disabled="busy" @click="emit('edit', entry)">编辑</button>
        <button class="secondary-button" :disabled="busy" @click="emit('history', entry)">
          版本历史
        </button>
      </div>
    </article>
    <p v-if="!entries.length" class="py-6 text-center text-sm text-muted-foreground">
      暂无词条。点击「新建词条」开始整理术语与别名。
    </p>
  </section>
</template>
