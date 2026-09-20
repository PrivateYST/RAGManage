<script setup lang="ts">
import type { KnowledgeBaseRow } from '../../../api/admin'
import { Database, Play, Search, SlidersHorizontal } from 'lucide-vue-next'
import { computed } from 'vue'

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
  props.knowledgeBases.find(item => item.id === knowledgeBaseId.value),
)

const searchActionHint = computed(() => {
  if (props.loading)
    return '正在加载知识库和发布版本…'
  if (!props.knowledgeBases.length)
    return '当前空间暂无知识库'
  if (!knowledgeBaseId.value)
    return '请先选择目标知识库'
  if (!selectedKnowledgeBase.value?.active_release_id)
    return '该知识库尚未发布 Release，发布后才能检索'
  if (!query.value.trim())
    return '请输入测试问题后运行检索'
  if (props.searching)
    return '正在当前 Release 中执行融合检索…'
  return '将在当前 Release 中融合召回证据，不会生成回答'
})
</script>

<template>
  <form class="search-query-card content-card" @submit.prevent="emit('submit')">
    <div class="search-query-main">
      <label class="search-field search-kb-field">
        <span><Database :size="13" aria-hidden="true" />目标知识库</span>
        <select v-model="knowledgeBaseId" :disabled="loading || searching">
          <option v-if="!knowledgeBases.length" value="">
            当前空间暂无知识库
          </option>
          <option v-for="knowledgeBase in knowledgeBases" :key="knowledgeBase.id" :value="knowledgeBase.id">
            {{ knowledgeBase.name }}{{ knowledgeBase.active_release_id ? ` · Release #${knowledgeBase.active_release_id}` : ' · 未发布' }}
          </option>
        </select>
      </label>

      <label class="search-field search-question-field">
        <span><Search :size="13" aria-hidden="true" />测试问题</span>
        <textarea
          v-model="query"
          rows="3"
          maxlength="2000"
          :disabled="searching"
          placeholder="输入真实业务问题，例如：出院结算需要携带哪些材料？"
        />
      </label>
    </div>

    <div class="search-query-options">
      <div class="search-option-heading">
        <SlidersHorizontal :size="13" aria-hidden="true" />
        <span>检索参数</span>
      </div>
      <label>
        <span>召回数量</span>
        <select v-model.number="topK" :disabled="searching">
          <option :value="5">Top 5</option>
          <option :value="10">Top 10</option>
          <option :value="15">Top 15</option>
          <option :value="20">Top 20</option>
        </select>
      </label>
      <label>
        <span>上下文上限</span>
        <select v-model.number="contextMaxChars" :disabled="searching">
          <option :value="3000">3,000 字符</option>
          <option :value="6000">6,000 字符</option>
          <option :value="10000">10,000 字符</option>
          <option :value="16000">16,000 字符</option>
        </select>
      </label>
      <button class="primary-button search-run-button" type="submit" :disabled="!canSearch">
        <span v-if="searching" class="loading-spinner" aria-hidden="true" />
        <Play v-else :size="14" aria-hidden="true" />
        {{ searching ? '正在检索…' : '运行检索' }}
      </button>
      <p class="search-run-hint" :class="{ ready: canSearch }" aria-live="polite">
        {{ searchActionHint }}
      </p>
    </div>
  </form>
</template>
