<script setup lang="ts">
import { RefreshCw, SearchCheck } from '@/components'
import SearchQueryForm from './components/SearchQueryForm.vue'
import SearchResultList from './components/SearchResultList.vue'
import { useSearchTest } from './index'
import './index.scss'

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
  error,
  result,
  loadKnowledgeBases,
  search,
} = useSearchTest()
</script>

<template>
  <section class="page-section search-test-page">
    <div class="page-intro">
      <div>
        <p class="eyebrow">
          检索与评测
        </p>
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
          :class="{ 'is-spinning': loadingKnowledgeBases }"
          :size="14"
          aria-hidden="true"
        />
        {{ loadingKnowledgeBases ? '刷新中…' : '刷新知识库' }}
      </button>
    </div>

    <div v-if="error" class="error-banner" role="alert">
      {{ error }}
    </div>

    <div v-if="selectedKnowledgeBase" class="search-release-context">
      <SearchCheck :size="14" aria-hidden="true" />
      <span>当前目标：<strong>{{ selectedKnowledgeBase.name }}</strong></span>
      <span v-if="selectedKnowledgeBase.active_release_id" class="status-pill ready">Release #{{ selectedKnowledgeBase.active_release_id }}</span>
      <span v-else class="status-pill draft">尚未发布</span>
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
