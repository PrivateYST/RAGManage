<script setup lang="ts">
import { Search, SlidersHorizontal } from 'lucide-vue-next'

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
  <div class="document-toolbar">
    <label class="document-search">
      <Search :size="15" aria-hidden="true" />
      <span class="sr-only">搜索文档</span>
      <input
        :value="props.query"
        placeholder="搜索文档名称"
        type="search"
        @input="emit('update:query', ($event.target as HTMLInputElement).value)"
      >
    </label>
    <label class="document-status-filter">
      <SlidersHorizontal :size="14" aria-hidden="true" />
      <span class="sr-only">筛选状态</span>
      <select :value="props.status" aria-label="筛选文档状态" @change="emit('update:status', ($event.target as HTMLSelectElement).value)">
        <option value="all">全部状态</option>
        <option value="complete">解析完成</option>
        <option value="partial">部分完成</option>
        <option value="processing">处理中</option>
        <option value="queued">等待处理</option>
        <option value="failed">解析失败</option>
        <option value="unsupported">不支持</option>
      </select>
    </label>
    <span class="table-count">共 {{ props.count }} 篇</span>
  </div>
</template>
