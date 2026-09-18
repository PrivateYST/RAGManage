<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const loginName = ref('')
const password = ref('')
const submitted = ref(false)
const canSubmit = computed(() => loginName.value.trim().length > 0 && password.value.length > 0 && !auth.loading)

async function submit(): Promise<void> {
  submitted.value = true
  if (!canSubmit.value)
    return
  if (await auth.signIn(loginName.value.trim(), password.value))
    await router.push('/dashboard')
}
</script>

<template>
  <main class="login-page">
    <section class="login-brand">
      <div class="brand-lockup">
        <span class="brand-mark">R</span><span>RAGManage</span>
      </div>
      <p>企业知识库管理与引用问答平台</p>
      <div class="login-value">
        <span>⌁</span><div><strong>从资料到答案</strong><small>每个回答都能回到明确的原文证据</small></div>
      </div>
      <div class="login-value">
        <span>◈</span><div><strong>空间级安全隔离</strong><small>客户资料、成员和会话相互独立</small></div>
      </div>
    </section>
    <section class="login-card" aria-labelledby="login-title">
      <div class="login-heading">
        <p class="eyebrow">
          欢迎回来
        </p><h1 id="login-title">
          登录工作台
        </h1><p>使用管理员为你开通的账号登录</p>
      </div>
      <form @submit.prevent="submit">
        <label for="login-name">账号</label><input id="login-name" v-model="loginName" autocomplete="username" placeholder="请输入账号">
        <label for="login-password">密码</label><input id="login-password" v-model="password" type="password" autocomplete="current-password" placeholder="请输入密码">
        <p v-if="submitted && !canSubmit" class="field-error">
          请输入账号和密码
        </p><p v-if="auth.error" class="field-error">
          {{ auth.error }}
        </p>
        <button class="primary-button login-submit" type="submit" :disabled="!canSubmit">
          {{ auth.loading ? '正在登录…' : '登录' }}
        </button>
      </form>
      <p class="login-footnote">
        账号由平台管理员创建。如需访问其他客户空间，请联系空间管理员授权。
      </p>
    </section>
  </main>
</template>
