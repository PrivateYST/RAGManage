<script setup lang="ts">
import { Search, SlidersHorizontal } from '@/components'

interface Props {
  query: string
  status: string
  count: number
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:query': [value: string]
  'update:status': [value: string]
}>()
</script>

<template>
  <div
    class="flex min-h-[55px] flex-wrap items-center gap-[12px] rounded-t-lg border border-border bg-card px-[14px] py-[10px]"
  >
    <label
      class="flex w-[min(300px,42vw)] items-center gap-[8px] text-muted-foreground max-sm:w-full"
    >
      <Search :size="15" aria-hidden="true" />
      <span class="sr-only">搜索文档</span>
      <input
        :value="props.query"
        class="h-[32px] w-full rounded-md border border-input bg-secondary px-[8px] text-[11px] text-foreground outline-none placeholder:text-muted-foreground focus:border-primary focus:bg-background focus:ring-2 focus:ring-primary/20"
        placeholder="搜索文档名称"
        type="search"
        @input="emit('update:query', ($event.target as HTMLInputElement).value)"
      />
    </label>
    <label class="flex items-center gap-[6px] text-muted-foreground">
      <SlidersHorizontal :size="14" aria-hidden="true" />
      <span class="sr-only">筛选状态</span>
      <select
        :value="props.status"
        class="h-[32px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        aria-label="筛选文档状态"
        @change="emit('update:status', ($event.target as HTMLSelectElement).value)"
      >
        <option value="all">全部状态</option>
        <option value="complete">解析完成</option>
        <option value="partial">部分完成</option>
        <option value="processing">处理中</option>
        <option value="queued">等待处理</option>
        <option value="failed">解析失败</option>
        <option value="unsupported">不支持</option>
      </select>
    </label>
    <span class="ml-auto text-[11px] text-muted-foreground max-sm:ml-0"
      >共 {{ props.count }} 篇</span
    >
  </div>
</template>
