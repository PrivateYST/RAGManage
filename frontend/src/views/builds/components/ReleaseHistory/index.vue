<script setup lang="ts">
import type { ReleaseHistoryEmits, ReleaseHistoryProps } from './type'
import { Eye, History, Radio, RotateCcw } from '@/components'
import { useReleaseHistory } from './index'
import './index.scss'

const props = defineProps<ReleaseHistoryProps>()
const emit = defineEmits<ReleaseHistoryEmits>()
const { formatDate, shortHash, providerLabel } = useReleaseHistory(props)
</script>

<template>
  <section class="release-history content-card">
    <header>
      <div><History :size="16" aria-hidden="true" /><strong>发布历史</strong></div>
      <span v-if="selectedKnowledgeBaseName">{{ selectedKnowledgeBaseName }}</span>
      <span v-else>选择具体知识库后查看</span>
    </header>
    <div v-if="loading" class="release-history-empty">
      正在加载发布历史…
    </div>
    <div v-else-if="!selectedKnowledgeBaseName" class="release-history-empty">
      请先在上方筛选一个知识库。
    </div>
    <div v-else-if="!releases.length" class="release-history-empty">
      当前知识库还没有 Release。
    </div>
    <div v-else class="release-history-list">
      <article v-for="release in releases" :key="release.id" :class="{ active: release.is_active }">
        <span class="release-history-status"><Radio v-if="release.is_active" :size="13" aria-hidden="true" /></span>
        <div>
          <strong>Release #{{ release.id }}</strong><small>构建 #{{ release.build_id }} · {{ release.document_count }} 份文档</small>
        </div>
        <div>
          <strong>{{ providerLabel(release.provider) }}</strong><small>Profile #{{ release.embedding_profile_id }} ·
            {{ shortHash(release.embedding_definition_hash) }}</small>
        </div>
        <div>
          <strong>{{ release.model_name }}</strong><small>{{ release.dimension }} 维 · {{ shortHash(release.model_revision) }}</small>
        </div>
        <time>{{ formatDate(release.created_at) }}</time>
        <span class="status-pill" :class="release.is_active ? 'ready' : 'retired'">{{
          release.is_active ? '当前使用' : '历史版本'
        }}</span>
        <div class="release-history-actions">
          <button class="release-view-button" type="button" @click="emit('view', release)">
            <Eye :size="13" aria-hidden="true" />查看详情
          </button>
          <button
            v-if="release.rollback_available"
            class="release-rollback-button"
            type="button"
            @click="emit('rollback', release)"
          >
            <RotateCcw :size="13" aria-hidden="true" />回退
          </button>
        </div>
      </article>
    </div>
  </section>
</template>
