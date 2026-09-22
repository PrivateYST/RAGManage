<script setup lang="ts">
import type { KnowledgeBaseRow } from '@/api/admin'
import { computed } from 'vue'
import { Database, Play, Search, SlidersHorizontal } from '@/components'

const props = defineProps<{
  knowledgeBases: KnowledgeBaseRow[]
  loading: boolean
  searching: boolean
  canSearch: boolean
}>()

const emit = defineEmits<{ submit: [] }>()
const knowledgeBaseId = defineModel<string>('knowledgeBaseId', { required: true })
const query = defineModel<string>('query', { required: true })
const topK = defineModel<number>('topK', { required: true })
const contextMaxChars = defineModel<number>('contextMaxChars', { required: true })

const selectedKnowledgeBase = computed(() =>
  props.knowledgeBases.find((item) => item.id === knowledgeBaseId.value),
)

const searchActionHint = computed(() => {
  if (props.loading) return '正在加载知识库和发布版本…'
  if (!props.knowledgeBases.length) return '当前空间暂无知识库'
  if (!knowledgeBaseId.value) return '请先选择目标知识库'
  if (!selectedKnowledgeBase.value?.active_release_id)
    return '该知识库尚未发布 Release，发布后才能检索'
  if (!query.value.trim()) return '请输入测试问题后运行检索'
  if (props.searching) return '正在当前 Release 中执行融合检索…'
  return '将在当前 Release 中融合召回证据，不会生成回答'
})
</script>

<template>
  <form
    class="content-card grid gap-[18px] p-[18px] lg:grid-cols-[minmax(0,1fr)_210px]"
    @submit.prevent="emit('submit')"
  >
    <div class="grid gap-[14px]">
      <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
        <span class="flex items-center gap-[6px]"
          ><Database :size="13" aria-hidden="true" />目标知识库</span
        >
        <select
          v-model="knowledgeBaseId"
          class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          :disabled="loading || searching"
        >
          <option v-if="!knowledgeBases.length" value="">当前空间暂无知识库</option>
          <option
            v-for="knowledgeBase in knowledgeBases"
            :key="knowledgeBase.id"
            :value="knowledgeBase.id"
          >
            {{ knowledgeBase.name
            }}{{
              knowledgeBase.active_release_id
                ? ` · Release #${knowledgeBase.active_release_id}`
                : ' · 未发布'
            }}
          </option>
        </select>
      </label>

      <label class="grid gap-[6px] text-[11px] font-semibold text-muted-foreground">
        <span class="flex items-center gap-[6px]"
          ><Search :size="13" aria-hidden="true" />测试问题</span
        >
        <textarea
          v-model="query"
          class="min-h-[82px] w-full resize-y rounded-md border border-input bg-background px-[10px] py-[10px] text-xs leading-[1.65] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          rows="3"
          maxlength="2000"
          :disabled="searching"
          placeholder="输入真实业务问题，例如：出院结算需要携带哪些材料？"
        />
      </label>
    </div>

    <div
      class="flex flex-col gap-[10px] border-l border-border pl-[18px] max-lg:border-l-0 max-lg:border-t max-lg:pl-0 max-lg:pt-[14px]"
    >
      <div class="flex items-center gap-[6px] text-[11px] font-bold text-foreground">
        <SlidersHorizontal :size="13" aria-hidden="true" />
        <span>检索参数</span>
      </div>
      <label class="grid gap-[6px] text-[10px] text-muted-foreground"
        ><span>召回数量</span
        ><select
          v-model.number="topK"
          class="h-[33px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          :disabled="searching"
        >
          <option :value="5">Top 5</option>
          <option :value="10">Top 10</option>
          <option :value="15">Top 15</option>
          <option :value="20">Top 20</option>
        </select>
      </label>
      <label class="grid gap-[6px] text-[10px] text-muted-foreground"
        ><span>上下文上限</span
        ><select
          v-model.number="contextMaxChars"
          class="h-[33px] rounded-md border border-input bg-background px-[8px] text-[11px] text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
          :disabled="searching"
        >
          <option :value="3000">3,000 字符</option>
          <option :value="6000">6,000 字符</option>
          <option :value="10000">10,000 字符</option>
          <option :value="16000">16,000 字符</option>
        </select>
      </label>
      <button
        class="search-run-button primary-button mt-auto w-full"
        type="submit"
        :disabled="!canSearch"
      >
        <span v-if="searching" class="loading-spinner" aria-hidden="true" />
        <Play v-else :size="14" aria-hidden="true" />
        {{ searching ? '正在检索…' : '运行检索' }}
      </button>
      <p
        class="search-run-hint min-h-[30px] -mt-[4px] text-[10px] leading-[1.5] text-status-warning"
        :class="canSearch ? 'text-muted-foreground' : ''"
        aria-live="polite"
      >
        {{ searchActionHint }}
      </p>
    </div>
  </form>
</template>
