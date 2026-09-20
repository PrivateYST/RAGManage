<!--
  404 页面职责：为不存在或无权限的路径提供明确反馈，并给出回到工作台的入口。
  该页面不依赖业务数据，因此在未登录状态下也可以安全渲染。
-->
<!-- eslint-disable vue/singleline-html-element-content-newline -->
<script setup lang="ts">
/* eslint-disable vue/singleline-html-element-content-newline */
import { useRouter } from 'vue-router'

const router = useRouter()

/** 返回受守卫保护的工作台入口，由路由守卫决定登录或默认菜单去向。 */
function backToWorkspace(): void {
  void router.push('/')
}
</script>

<template>
  <main class="not-found-page">
    <section class="not-found-card" aria-labelledby="not-found-title">
      <p class="eyebrow">页面不存在</p>
      <h1 id="not-found-title">找不到这个页面</h1>
      <p>链接可能已失效，或者你当前没有访问这个菜单的权限。</p>
      <button class="primary-button" type="button" @click="backToWorkspace">返回工作台</button>
    </section>
  </main>
</template>

<style scoped>
.not-found-page {
  display: grid;
  min-height: 100vh;
  place-items: center;
  padding: 24px;
  background: #f8fafc;
}

.not-found-card {
  width: min(100%, 460px);
  padding: 40px;
  text-align: center;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 16px;
  box-shadow: 0 12px 32px rgb(15 23 42 / 8%);
}

.not-found-card h1 {
  margin: 8px 0 12px;
  color: var(--primary);
  font-size: 26px;
}

.not-found-card p:not(.eyebrow) {
  margin: 0 0 24px;
  color: var(--muted);
}
</style>
