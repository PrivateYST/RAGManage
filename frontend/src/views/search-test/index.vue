<script setup lang="ts">
import { RefreshCw, SearchCheck } from '@/components'
import SearchQueryForm from './components/SearchQueryForm.vue'
import SearchResultList from './components/SearchResultList.vue'
import { useSearchTest } from './index'

const {
  knowledgeBases,
  knowledgeBaseId,
  selectedKnowledgeBase,
  query,
  topK,
  contextMaxChars,
  loadingKnowledgeBases,
  searching,
  canSearch,
  result,
  loadKnowledgeBases,
  search,
} = useSearchTest()
</script>

<template>
  <section class="mx-auto w-full max-w-[1160px] pb-[28px]">
    <div class="page-intro">
      <div>
        <p class="eyebrow">检索与评测</p>
        <h1>检索调试</h1>
        <p class="page-description">
          在当前发布版本中运行向量与关键词融合检索，检查证据、排名、过滤范围和原文定位。
        </p>
      </div>
      <button
        class="secondary-button"
        type="button"
        :disabled="loadingKnowledgeBases || searching"
        title="重新读取当前空间的知识库及其 Release 状态"
        @click="loadKnowledgeBases"
      >
        <RefreshCw
          :class="{ 'animate-spin': loadingKnowledgeBases }"
          :size="14"
          aria-hidden="true"
        />
        {{ loadingKnowledgeBases ? '刷新中…' : '刷新知识库' }}
      </button>
    </div>

    <div
      v-if="selectedKnowledgeBase"
      class="mb-[12px] flex min-h-[42px] items-center gap-[8px] rounded-md border border-primary/20 bg-primary/5 px-[14px] text-[11px] text-primary"
    >
      <SearchCheck :size="14" aria-hidden="true" />
      <span
        >当前目标：<strong>{{ selectedKnowledgeBase.name }}</strong></span
      >
      <span
        v-if="selectedKnowledgeBase.active_release_id"
        class="ml-auto inline-flex min-h-[20px] items-center rounded-full bg-status-up-soft px-[8px] text-[10px] font-medium text-status-up"
        >Release #{{ selectedKnowledgeBase.active_release_id }}</span
      >
      <span
        v-else
        class="ml-auto inline-flex min-h-[20px] items-center rounded-full bg-status-warning-soft px-[8px] text-[10px] font-medium text-status-warning"
        >尚未发布</span
      >
    </div>

    <SearchQueryForm
      v-model:knowledge-base-id="knowledgeBaseId"
      v-model:query="query"
      v-model:top-k="topK"
      v-model:context-max-chars="contextMaxChars"
      :knowledge-bases="knowledgeBases"
      :loading="loadingKnowledgeBases"
      :searching="searching"
      :can-search="canSearch"
      @submit="search"
    />

    <SearchResultList :result="result" :searching="searching" />
  </section>
</template>
