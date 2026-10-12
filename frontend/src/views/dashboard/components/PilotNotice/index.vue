<!-- 工作台试点提示：集中展示平台数据使用范围与问答能力说明。 -->
<script setup lang="ts">
import { ArrowUpRight } from '@/components'
import { PILOT_NOTICE } from './index'
import './index.scss'
</script>

<template>
  <div
    class="flex items-center gap-[12px] rounded-md border border-primary/20 bg-primary/5 px-[14px] py-[12px] text-primary max-sm:flex-col max-sm:items-start max-sm:gap-[6px]"
  >
    <span class="shrink-0 text-[11px] font-semibold">试点提示</span>
    <p class="mb-0 flex-1 text-[11px] text-primary/80">{{ PILOT_NOTICE }}</p>
    <RouterLink
      class="inline-flex items-center gap-[4px] text-[11px] font-semibold text-primary"
      to="/chat"
    >
      去提问
      <ArrowUpRight :size="14" />
    </RouterLink>
  </div>
</template>
