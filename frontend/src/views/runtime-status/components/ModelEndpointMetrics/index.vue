<!-- 模型端点指标展示：提供可用性聚合数，不列出端点配置。 -->
<script setup lang="ts">
import type { ModelEndpointMetricsProps } from './type'
import './index.scss'

defineProps<ModelEndpointMetricsProps>()
</script>

<template>
  <section class="content-card" aria-labelledby="runtime-models-title">
    <h2 id="runtime-models-title">模型端点</h2>
    <dl class="mt-[16px] grid gap-[8px] text-sm">
      <div class="flex justify-between">
        <dt>正常</dt>
        <dd>{{ metrics.healthy }}</dd>
      </div>
      <div class="flex justify-between">
        <dt>异常</dt>
        <dd>{{ metrics.unhealthy }}</dd>
      </div>
      <div class="flex justify-between">
        <dt>未知</dt>
        <dd>{{ metrics.unknown }}</dd>
      </div>
    </dl>
  </section>
</template>
