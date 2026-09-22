<!-- 登录页只负责收集凭据和提交认证；登录后的默认业务入口由动态路由守卫决定。 -->
<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

const router = useRouter()
const auth = useAuthStore()
const toast = useAppToast()
const loginName = shallowRef('')
const password = shallowRef('')
const submitted = shallowRef(false)
const canSubmit = computed(
  () => loginName.value.trim().length > 0 && password.value.length > 0 && !auth.loading,
)

/** 提交登录凭据；失败消息通过全局 Toast 告知，不在表单下堆叠临时提示条。 */
async function submit(): Promise<void> {
  submitted.value = true
  if (!canSubmit.value) return
  if (await auth.signIn(loginName.value.trim(), password.value)) await router.push('/')
  else toast.error(auth.error || '登录失败，请稍后重试')
}
</script>

<template>
  <main
    class="grid h-screen min-h-screen overflow-y-auto bg-[#fafafa] lg:grid-cols-[minmax(0,1fr)_430px]"
  >
    <section
      class="flex min-h-[250px] flex-col justify-center bg-foreground px-[28px] pb-[30px] pt-[40px] text-background sm:px-[48px] lg:min-h-full lg:px-[13%] lg:py-[12%]"
    >
      <div class="flex items-center gap-[10px]">
        <span
          class="grid size-[32px] place-items-center rounded-lg bg-background text-lg font-bold text-foreground"
          >R</span
        >
        <span class="text-base font-semibold">RAGManage</span>
      </div>
      <p
        class="mb-0 mt-[16px] max-w-[360px] text-[15px] text-background/60 lg:mb-[62px] lg:mt-[22px]"
      >
        企业知识库管理与引用问答平台
      </p>
      <div class="hidden max-w-[360px] lg:block">
        <div class="my-[16px] flex items-start gap-[13px]">
          <span
            class="grid size-[26px] place-items-center rounded-md border border-[#3f3f46] text-sm text-[#d4d4d8]"
            >⌁</span
          >
          <div>
            <strong class="block text-xs font-medium">从资料到答案</strong
            ><small class="mt-[2px] block text-[11px] text-[#71717a]"
              >每个回答都能回到明确的原文证据</small
            >
          </div>
        </div>
        <div class="my-[16px] flex items-start gap-[13px]">
          <span
            class="grid size-[26px] place-items-center rounded-md border border-[#3f3f46] text-sm text-[#d4d4d8]"
            >◈</span
          >
          <div>
            <strong class="block text-xs font-medium">空间级安全隔离</strong
            ><small class="mt-[2px] block text-[11px] text-[#71717a]"
              >客户资料、成员和会话相互独立</small
            >
          </div>
        </div>
      </div>
    </section>

    <section
      class="flex w-full items-center justify-center px-0 py-[42px]"
      aria-labelledby="login-title"
    >
      <div class="w-[min(calc(100%-44px),380px)] lg:w-[min(calc(100%-64px),330px)]">
        <div class="mb-[30px]">
          <p class="mb-[7px] text-[11px] tracking-[0.04em] text-muted-foreground">欢迎回来</p>
          <h1 id="login-title" class="mb-[7px] text-[25px] font-semibold leading-tight">
            登录工作台
          </h1>
          <p class="mb-0 text-xs text-muted-foreground">使用管理员为你开通的账号登录</p>
        </div>
        <form class="flex flex-col" @submit.prevent="submit">
          <label class="mb-[6px] mt-[14px] text-xs font-medium text-[#3f3f46]" for="login-name"
            >账号</label
          >
          <input
            id="login-name"
            v-model="loginName"
            class="h-[40px] w-full rounded-md border border-border bg-background px-[11px] text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20"
            autocomplete="username"
            placeholder="请输入账号"
          />
          <label class="mb-[6px] mt-[14px] text-xs font-medium text-[#3f3f46]" for="login-password"
            >密码</label
          >
          <input
            id="login-password"
            v-model="password"
            class="h-[40px] w-full rounded-md border border-border bg-background px-[11px] text-xs text-foreground outline-none transition-colors placeholder:text-muted-foreground focus:border-ring focus:ring-2 focus:ring-ring/20"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
          />
          <p v-if="submitted && !canSubmit" class="field-error">请输入账号和密码</p>
          <button
            class="primary-button mt-[22px] h-[40px] w-full"
            type="submit"
            :disabled="!canSubmit"
          >
            {{ auth.loading ? '正在登录…' : '登录' }}
          </button>
        </form>
        <p class="mt-[30px] text-[10px] leading-[1.7] text-[#a1a1aa]">
          账号由平台管理员创建。如需访问其他客户空间，请联系空间管理员授权。
        </p>
      </div>
    </section>
  </main>
</template>
