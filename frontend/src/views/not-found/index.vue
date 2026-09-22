<!--
  404 页面职责：为不存在或无权限的路径提供明确反馈，并给出回到工作台的入口。
  该页面不依赖业务数据，因此在未登录状态下也可以安全渲染。
-->
<!-- eslint-disable vue/singleline-html-element-content-newline -->
<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()

/** 返回受守卫保护的工作台入口，由路由守卫决定登录或默认菜单去向。 */
function backToWorkspace(): void {
  void router.push('/')
}
</script>

<template>
  <main class="grid min-h-screen place-items-center bg-canvas p-[24px]">
    <section
      class="w-full max-w-[460px] rounded-2xl border border-border bg-card p-[40px] text-center shadow-[0_12px_32px_rgb(15_23_42_/_8%)]"
      aria-labelledby="not-found-title"
    >
      <p class="eyebrow">页面不存在</p>
      <h1 id="not-found-title" class="mb-[12px] mt-[8px] text-[26px] font-semibold text-primary">
        找不到这个页面
      </h1>
      <p class="mb-[24px] text-sm text-muted-foreground">
        链接可能已失效，或者你当前没有访问这个菜单的权限。
      </p>
      <button class="primary-button" type="button" @click="backToWorkspace">返回工作台</button>
    </section>
  </main>
</template>
