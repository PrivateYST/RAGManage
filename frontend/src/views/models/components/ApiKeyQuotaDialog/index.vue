<!-- 额度弹窗提供 Token 加减选择、实时余额预览和请求期间的明确忙碌反馈。 -->
<script setup lang="ts">
import type { ApiKeyQuotaDialogEmits, ApiKeyQuotaDialogProps } from './type'
import { AppDialog, SlidersHorizontal } from '@/components'
import { useApiKeyQuotaDialog } from './index'

const props = defineProps<ApiKeyQuotaDialogProps>()
const emit = defineEmits<ApiKeyQuotaDialogEmits>()
const { form, error, nextTokenLimit, nextTokenRemaining, maxAmount, submit } =
  useApiKeyQuotaDialog(props)

/** 前端校验通过后只提交新的总额度，最终并发安全校验由服务端负责。 */
function handleSubmit(): void {
  const adjustment = submit()
  if (adjustment !== null) emit('submit', adjustment)
}
</script>

<template>
  <AppDialog
    :open="open"
    title="调整 API Key 额度"
    description="为已发放的医院模型网关 Key 增加或减少 Token 总额度。"
    content-class="w-[min(480px,calc(100vw-2rem))]"
    :dismissible="!busy"
    @close="emit('close')"
  >
    <section
      v-if="apiKey"
      class="w-full rounded-lg border border-border bg-card p-[20px] text-foreground shadow-[0_18px_48px_rgb(40_36_58_/_18%)]"
    >
      <header class="flex items-center gap-[10px]">
        <SlidersHorizontal :size="17" class="text-muted-foreground" />
        <div>
          <p class="eyebrow">医院网关 Key</p>
          <h2 class="mt-[2px] text-[17px] font-semibold">调整 API Key 额度</h2>
        </div>
      </header>
      <p class="mt-[12px] text-xs leading-5 text-muted-foreground">
        {{ apiKey.tenant_name }} · {{ apiKey.name }}。额度按嵌入输入、生成输入和生成输出 Token
        合计扣减。
      </p>
      <form
        class="mt-[16px] flex flex-col gap-[14px]"
        :aria-busy="busy"
        @submit.prevent="handleSubmit"
      >
        <label class="flex flex-col gap-[6px] text-xs font-medium">
          调整方式
          <select
            v-model="form.operation"
            class="h-9 rounded-md border border-input bg-background px-3 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            :disabled="busy"
            aria-label="选择额度调整方式"
          >
            <option value="add">增加额度</option>
            <option value="subtract">减少额度</option>
          </select>
        </label>
        <label class="flex flex-col gap-[6px] text-xs font-medium">
          {{ form.operation === 'add' ? '增加 Token' : '减少 Token' }}
          <input
            v-model="form.amount"
            type="number"
            min="1"
            :max="maxAmount"
            step="1"
            required
            inputmode="numeric"
            class="h-9 rounded-md border border-input bg-background px-3 text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            :disabled="busy || maxAmount < 1"
            :aria-invalid="error ? 'true' : 'false'"
            :aria-describedby="error ? 'api-key-quota-error' : 'api-key-quota-help'"
          />
          <small id="api-key-quota-help" class="text-[11px] font-normal text-muted-foreground">
            当前总额度 {{ apiKey.token_limit.toLocaleString() }}；最多可{{
              form.operation === 'add' ? '增加' : '减少'
            }}
            {{ maxAmount.toLocaleString() }} Token。
          </small>
        </label>
        <div
          class="grid grid-cols-2 gap-[10px] rounded-md border border-border bg-muted/30 p-[12px] text-xs"
        >
          <div>
            <span class="block text-muted-foreground">调整后总额度</span>
            <strong class="mt-[3px] block tabular-nums">{{
              nextTokenLimit.toLocaleString()
            }}</strong>
          </div>
          <div>
            <span class="block text-muted-foreground">调整后可用余额</span>
            <strong class="mt-[3px] block tabular-nums">{{
              nextTokenRemaining.toLocaleString()
            }}</strong>
          </div>
        </div>
        <p class="text-[11px] leading-4 text-muted-foreground">
          减少额度不能低于已用 {{ apiKey.token_used.toLocaleString() }} 与并发预留
          {{ apiKey.token_reserved.toLocaleString() }} Token 之和。
        </p>
        <p
          v-if="error"
          id="api-key-quota-error"
          class="text-xs text-destructive"
          role="alert"
          aria-live="polite"
        >
          {{ error }}
        </p>
        <footer class="flex justify-end gap-[8px] pt-[2px]">
          <button type="button" class="secondary-button" :disabled="busy" @click="emit('close')">
            取消
          </button>
          <button
            type="submit"
            class="primary-button"
            :disabled="busy || maxAmount < 1"
            :aria-busy="busy"
          >
            <span v-if="busy" role="status" aria-live="polite">保存中…</span>
            <template v-else>保存额度</template>
          </button>
        </footer>
      </form>
    </section>
  </AppDialog>
</template>
