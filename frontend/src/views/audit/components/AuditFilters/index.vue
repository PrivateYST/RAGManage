<!-- 操作日志筛选栏：不读取权限或发起请求，由页面提供状态和回调。 -->
<script setup lang="ts">
import type { AuditFiltersEmits, AuditFiltersProps } from './type'
import { Filter, RotateCcw, Search } from '@/components'
import { auditActionOptions, auditTargetOptions } from '../../enum'
import './index.scss'

/** 页面拥有筛选状态；平台范围选项仅由授权后的页面状态决定是否展示。 */
defineProps<AuditFiltersProps>()
const emit = defineEmits<AuditFiltersEmits>()
</script>

<template>
  <form
    class="content-card mb-[14px] grid items-end gap-[12px] p-[16px] lg:grid-cols-[190px_180px_180px_minmax(180px,1fr)_auto]"
    @submit.prevent="emit('submit')"
  >
    <div class="flex items-center gap-[8px] lg:hidden">
      <span class="grid size-[30px] place-items-center rounded-md bg-primary/10 text-primary">
        <Filter :size="15" aria-hidden="true" />
      </span>
      <div>
        <strong class="block text-xs">筛选日志</strong>
        <small class="mt-[2px] block text-[9px] text-muted-foreground"
          >筛选条件只作用于当前日志范围</small
        >
      </div>
    </div>
    <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
      <span>日志范围</span>
      <select
        :value="scope"
        class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        @change="
          emit(
            'update:scope',
            ($event.target as HTMLSelectElement).value as AuditFiltersProps['scope'],
          )
        "
      >
        <option value="space">当前空间 · {{ spaceName || '未选择' }}</option>
        <option v-if="isPlatformAdmin" value="platform">平台级配置</option>
      </select>
    </label>
    <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
      <span>操作类型</span>
      <select
        :value="actionPrefix"
        class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        @change="emit('update:actionPrefix', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="option in auditActionOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
    </label>
    <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
      <span>目标对象</span>
      <select
        :value="targetType"
        class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
        @change="emit('update:targetType', ($event.target as HTMLSelectElement).value)"
      >
        <option v-for="option in auditTargetOptions" :key="option.value" :value="option.value">
          {{ option.label }}
        </option>
      </select>
    </label>
    <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
      <span>操作人</span>
      <div class="relative">
        <Search
          class="absolute left-[10px] top-[10px] text-muted-foreground"
          :size="14"
          aria-hidden="true"
        />
        <input
          :value="actor"
          class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] pl-[32px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          maxlength="100"
          placeholder="姓名或登录名"
          @input="emit('update:actor', ($event.target as HTMLInputElement).value)"
        />
      </div>
    </label>
    <div class="flex gap-[8px] max-lg:justify-end max-sm:col-span-1 max-sm:[&>button]:flex-1">
      <button class="secondary-button" type="button" :disabled="loading" @click="emit('reset')">
        <RotateCcw :size="14" aria-hidden="true" />重置
      </button>
      <button class="primary-button" type="submit" :disabled="loading">
        <Search :size="14" aria-hidden="true" />查询
      </button>
    </div>
  </form>
</template>
