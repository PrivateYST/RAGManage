<!-- 任务筛选子视图：仅呈现可用筛选项，并向页面回传用户选择。 -->
<script setup lang="ts">
import type { TaskFiltersEmits, TaskFiltersProps } from './type'
import './index.scss'

defineProps<TaskFiltersProps>()
const emit = defineEmits<TaskFiltersEmits>()
</script>

<template>
  <div class="content-card mb-[12px] flex flex-wrap items-center gap-[12px] p-[12px]">
    <label class="flex items-center gap-[8px] text-[11px] text-muted-foreground">
      知识库
      <select
        :value="knowledgeBaseId"
        class="h-[32px] min-w-[150px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        @change="emit('update:knowledgeBaseId', ($event.target as HTMLSelectElement).value)"
      >
        <option value="all">全部知识库</option>
        <option
          v-for="knowledgeBase in knowledgeBases"
          :key="knowledgeBase.id"
          :value="knowledgeBase.id"
        >
          {{ knowledgeBase.name }}
        </option>
      </select>
    </label>
    <label class="flex items-center gap-[8px] text-[11px] text-muted-foreground">
      状态
      <select
        :value="stateFilter"
        class="h-[32px] min-w-[120px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        @change="emit('update:stateFilter', ($event.target as HTMLSelectElement).value)"
      >
        <option value="all">全部状态</option>
        <option value="queued">排队中</option>
        <option value="running">处理中</option>
        <option value="completed">已完成</option>
        <option value="failed">失败</option>
        <option value="cancelled">已取消</option>
      </select>
    </label>
    <span class="ml-auto text-[11px] text-muted-foreground">共 {{ visibleTaskCount }} 个任务</span>
  </div>
</template>
