<!-- 文件存储指标展示：仅展示聚合容量，不展示文件或空间明细。 -->
<script setup lang="ts">
import type { FileStorageMetricsProps } from './type'
import { formatBytes } from '../../index'
import './index.scss'

defineProps<FileStorageMetricsProps>()
</script>

<template>
  <section class="content-card" aria-labelledby="runtime-storage-title">
    <h2 id="runtime-storage-title">文件存储</h2>
    <dl class="mt-[16px] grid gap-[8px] text-sm">
      <div class="flex justify-between">
        <dt>已使用</dt>
        <dd>{{ formatBytes(metrics.used_bytes) }}</dd>
      </div>
      <div class="flex justify-between">
        <dt>可用</dt>
        <dd>{{ formatBytes(metrics.free_bytes) }}</dd>
      </div>
      <div class="flex justify-between">
        <dt>总量</dt>
        <dd>{{ formatBytes(metrics.total_bytes) }}</dd>
      </div>
    </dl>
  </section>
</template>
