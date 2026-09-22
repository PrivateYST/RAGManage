<!-- 环境检查页：只负责页面标题和服务状态子组件的组合。 -->
<script setup lang="ts">
import EnvironmentStatus from '@/views/environment/components/EnvironmentStatus.vue'
</script>

<template>
  <section class="page-section">
    <p class="eyebrow">工程基础 · P02</p>
    <h1>环境检查</h1>
    <p class="page-description">验证本地服务连接。知识库管理与问答功能将在后续阶段接入。</p>
    <EnvironmentStatus />
  </section>
</template>
