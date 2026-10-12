<!-- 环境检查页面：组合页面说明与基础服务状态展示，不承载请求细节。 -->
<script setup lang="ts">
import EnvironmentStatus from './components/EnvironmentStatus/index.vue'
import { useEnvironmentPage } from './index'
import './index.scss'

const { errorMessage, health, loading, refresh } = useEnvironmentPage()
</script>

<template>
  <section class="page-section">
    <p class="eyebrow">工程基础 · P02</p>
    <h1>环境检查</h1>
    <p class="page-description">验证本地服务连接。知识库管理与问答功能将在后续阶段接入。</p>
    <EnvironmentStatus
      :error-message="errorMessage"
      :health="health"
      :loading="loading"
      @refresh="refresh"
    />
  </section>
</template>
