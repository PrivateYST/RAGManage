<!-- 医院管理员粘贴系统分配的 Key；组件只呈现脱敏状态并委托同目录逻辑完成交接确认。 -->
<script setup lang="ts">
import type { TenantApiKeyConfigProps } from './type'
import { toRef } from 'vue'
import { KeyRound, RefreshCw, ShieldCheck } from '@/components'
import { useTenantApiKeyConfig } from './index'

const props = defineProps<TenantApiKeyConfigProps>()
const emit = defineEmits<{ configured: [] }>()
const { configuration, loading, submitting, apiKey, showApiKey, error, canSubmit, load, submit } =
  useTenantApiKeyConfig(toRef(props, 'tenantId'))

/** 确认成功后通知外层弹窗关闭；失败时保留输入和错误信息便于修正。 */
async function handleSubmit(): Promise<void> {
  if (await submit()) emit('configured')
}
</script>

<template>
  <section class="content-card flex flex-col gap-[16px]">
    <header class="flex flex-wrap items-start justify-between gap-[12px]">
      <div>
        <p class="eyebrow">{{ tenantName || '当前医院' }} / 模型服务</p>
        <h2 class="text-base font-semibold text-foreground">医院 API Key 配置</h2>
        <p class="mt-[5px] max-w-[720px] text-xs leading-5 text-muted-foreground">
          请粘贴系统管理员为本医院创建并通过安全渠道分配的
          <code>sk-</code> Key。平台会核验它是否属于当前医院， 只记录交接确认状态，不保存或回显 Key
          明文。
        </p>
      </div>
      <button class="secondary-button" type="button" :disabled="loading" @click="load">
        <RefreshCw :size="14" />刷新状态
      </button>
    </header>

    <div
      v-if="loading"
      class="grid min-h-[112px] place-content-center text-xs text-muted-foreground"
      role="status"
    >
      正在读取医院 Key 状态…
    </div>
    <div
      v-else-if="error && !configuration"
      class="flex flex-col items-start gap-[10px]"
      role="alert"
    >
      <p class="text-xs text-destructive">{{ error }}</p>
      <button class="secondary-button" type="button" @click="load">重新加载</button>
    </div>
    <div
      v-else-if="!configuration?.key_prefix"
      class="rounded-md border border-border bg-muted/30 p-[14px]"
    >
      <strong class="block text-sm font-medium text-foreground">尚未分配医院 Key</strong>
      <p class="mt-[4px] text-xs leading-5 text-muted-foreground">
        请联系系统管理员，在“空间管理”中为 {{ tenantName || '当前医院' }} 创建并安全发放 API Key。
      </p>
    </div>
    <template v-else>
      <div
        class="flex flex-wrap items-center justify-between gap-[10px] rounded-md border border-border bg-muted/30 px-[14px] py-[12px]"
      >
        <div>
          <span class="block text-[11px] text-muted-foreground">系统分配的医院 Key</span>
          <code class="mt-[3px] block text-xs">{{ configuration.key_prefix }}</code>
        </div>
        <span
          class="inline-flex items-center gap-[5px] rounded-full border px-[9px] py-[4px] text-[11px]"
          :class="
            configuration.configured
              ? 'border-status-up/30 bg-status-up-soft text-status-up'
              : 'border-border bg-background text-muted-foreground'
          "
        >
          <ShieldCheck v-if="configuration.configured" :size="13" />
          {{ configuration.configured ? '已确认配置' : '待医院确认' }}
        </span>
        <p v-if="configuration.status !== 'active'" class="w-full text-xs text-destructive">
          当前 Key 状态为 {{ configuration.status }}，请联系系统管理员检查或重新分配。
        </p>
      </div>

      <form
        class="flex flex-col gap-[10px]"
        :aria-busy="submitting ? 'true' : 'false'"
        @submit.prevent="handleSubmit"
      >
        <label
          class="flex flex-col gap-[6px] text-xs font-medium text-foreground"
          for="tenant-api-key-input"
        >
          粘贴系统管理员分配的完整 Key
          <span
            class="flex h-[38px] items-center gap-[8px] rounded-md border border-input bg-background px-[10px] focus-within:ring-2 focus-within:ring-ring/40"
          >
            <KeyRound :size="14" class="shrink-0 text-muted-foreground" aria-hidden="true" />
            <input
              id="tenant-api-key-input"
              v-model="apiKey"
              class="min-w-0 flex-1 bg-transparent font-mono text-xs text-foreground outline-none placeholder:text-muted-foreground"
              :type="showApiKey ? 'text' : 'password'"
              autocomplete="off"
              maxlength="500"
              placeholder="sk-…"
              required
              :disabled="!canSubmit || submitting"
              :aria-invalid="error ? 'true' : 'false'"
              :aria-describedby="error ? 'tenant-api-key-error' : 'tenant-api-key-help'"
            />
            <button
              class="shrink-0 text-[11px] text-muted-foreground hover:text-foreground"
              type="button"
              :disabled="!canSubmit || submitting"
              @click="showApiKey = !showApiKey"
            >
              {{ showApiKey ? '隐藏' : '显示' }}
            </button>
          </span>
        </label>
        <small id="tenant-api-key-help" class="text-[11px] text-muted-foreground">
          关闭页面或确认成功后，输入框中的 Key 会被清除。请勿在此粘贴全局模型网关 Key。
        </small>
        <p
          v-if="error"
          id="tenant-api-key-error"
          class="text-xs text-destructive"
          role="alert"
          aria-live="polite"
        >
          {{ error }}
        </p>
        <div class="flex justify-end">
          <button
            class="primary-button"
            type="submit"
            :disabled="!canSubmit || submitting || !apiKey.trim()"
            :aria-busy="submitting ? 'true' : 'false'"
          >
            <span v-if="submitting" role="status" aria-live="polite">核验并保存中…</span>
            <template v-else>核验并确认配置</template>
          </button>
        </div>
      </form>
    </template>
  </section>
</template>
