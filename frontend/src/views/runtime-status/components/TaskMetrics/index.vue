<!-- 任务指标展示：只呈现平台聚合计数，不暴露任务记录。 -->
<script setup lang="ts">
import type { TaskMetricsProps } from './type'
import './index.scss'

defineProps<TaskMetricsProps>()
</script>

<template>
  <section class="content-card" aria-labelledby="runtime-tasks-title">
    <h2 id="runtime-tasks-title">任务</h2>
    <dl class="mt-[16px] grid gap-[8px] text-sm">
      <div class="flex justify-between">
        <dt>排队中</dt>
        <dd>{{ metrics.queued ?? 0 }}</dd>
      </div>
      <div class="flex justify-between">
        <dt>运行中</dt>
        <dd>{{ metrics.running ?? 0 }}</dd>
      </div>
      <div class="flex justify-between">
        <dt>失败</dt>
        <dd>{{ metrics.failed ?? 0 }}</dd>
      </div>
    </dl>
  </section>
</template>
