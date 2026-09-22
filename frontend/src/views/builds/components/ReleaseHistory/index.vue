<script setup lang="ts">
import type { ReleaseHistoryEmits, ReleaseHistoryProps } from './type'
import type { ReleaseRow } from '@/api/builds'
import type { AppTableColumn } from '@/components'
import { AppTable, Eye, History, Radio, RotateCcw } from '@/components'
import { useReleaseHistory } from './index'
import './index.scss'

const props = defineProps<ReleaseHistoryProps>()
const emit = defineEmits<ReleaseHistoryEmits>()
const { formatDate, shortHash, providerLabel } = useReleaseHistory(props)
const columns: AppTableColumn<ReleaseRow>[] = [
  { key: 'release', title: '发布版本' },
  { key: 'provider', title: '接入配置' },
  { key: 'model', title: '模型' },
  { key: 'created', title: '创建时间' },
  { key: 'status', title: '状态' },
  { key: 'actions', title: '操作' },
]
</script>

<template>
  <section class="release-history content-card">
    <header>
      <div><History :size="16" aria-hidden="true" /><strong>发布历史</strong></div>
      <span v-if="selectedKnowledgeBaseName">{{ selectedKnowledgeBaseName }}</span>
      <span v-else>选择具体知识库后查看</span>
    </header>
    <div v-if="loading" class="release-history-empty">正在加载发布历史…</div>
    <div v-else-if="!selectedKnowledgeBaseName" class="release-history-empty">
      请先在上方筛选一个知识库。
    </div>
    <div v-else-if="!releases.length" class="release-history-empty">当前知识库还没有 Release。</div>
    <AppTable v-else :rows="releases" :columns="columns" row-key="id" class="release-history-table">
      <template #cell-release="{ row: release }"
        ><div class="release-history-status">
          <Radio v-if="release.is_active" :size="13" aria-hidden="true" />
        </div>
        <div>
          <strong>Release #{{ release.id }}</strong
          ><small>构建 #{{ release.build_id }} · {{ release.document_count }} 份文档</small>
        </div></template
      >
      <template #cell-provider="{ row: release }"
        ><strong>{{ providerLabel(release.provider) }}</strong
        ><small
          >Profile #{{ release.embedding_profile_id }} ·
          {{ shortHash(release.embedding_definition_hash) }}</small
        ></template
      >
      <template #cell-model="{ row: release }"
        ><strong>{{ release.model_name }}</strong
        ><small
          >{{ release.dimension }} 维 · {{ shortHash(release.model_revision) }}</small
        ></template
      >
      <template #cell-created="{ row: release }">{{ formatDate(release.created_at) }}</template>
      <template #cell-status="{ row: release }"
        ><span class="status-pill" :class="release.is_active ? 'ready' : 'retired'">{{
          release.is_active ? '当前使用' : '历史版本'
        }}</span></template
      >
      <template #cell-actions="{ row: release }"
        ><div class="release-history-actions">
          <button class="release-view-button" type="button" @click="emit('view', release)">
            <Eye :size="13" aria-hidden="true" />查看详情</button
          ><button
            v-if="release.rollback_available"
            class="release-rollback-button"
            type="button"
            @click="emit('rollback', release)"
          >
            <RotateCcw :size="13" aria-hidden="true" />回退
          </button>
        </div></template
      >
      <!-- 发布历史以列定义渲染，保持统一表头、行高和分页行为。 -->
      <!--
        <span class="release-history-status"
          ><Radio v-if="release.is_active" :size="13" aria-hidden="true"
        /></span>
        <div>
          <strong>Release #{{ release.id }}</strong
          ><small>构建 #{{ release.build_id }} · {{ release.document_count }} 份文档</small>
        </div>
        <div>
          <strong>{{ providerLabel(release.provider) }}</strong
          ><small
            >Profile #{{ release.embedding_profile_id }} ·
            {{ shortHash(release.embedding_definition_hash) }}</small
          >
        </div>
        <div>
          <strong>{{ release.model_name }}</strong
          ><small>{{ release.dimension }} 维 · {{ shortHash(release.model_revision) }}</small>
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
        </article> -->
    </AppTable>
  </section>
</template>
