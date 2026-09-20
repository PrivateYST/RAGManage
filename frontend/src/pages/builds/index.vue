<script setup lang="ts">
import { Box, CheckCircle2, Cpu, DatabaseZap, RefreshCw, Rocket, TriangleAlert } from 'lucide-vue-next'
import CreateBuildDialog from './components/CreateBuildDialog/index.vue'
import ReleaseDetailDialog from './components/ReleaseDetailDialog/index.vue'
import ReleaseDiffDialog from './components/ReleaseDiffDialog/index.vue'
import ReleaseHistory from './components/ReleaseHistory/index.vue'
import ReleaseRollbackDialog from './components/ReleaseRollbackDialog/index.vue'
import { useBuildsPage } from './index'
import './index.scss'

const {
  knowledgeBases,
  visibleBuilds,
  releases,
  currentRelease,
  knowledgeBaseId,
  selectedKnowledgeBase,
  initialCreateKnowledgeBaseId,
  loading,
  creating,
  createDialogOpen,
  releaseDialogOpen,
  releasePreview,
  releaseDetailOpen,
  selectedRelease,
  releaseBuildDetail,
  loadingReleaseDetail,
  releaseDetailError,
  rollbackDialogOpen,
  rollbackTarget,
  rollingBack,
  previewingRelease,
  publishingRelease,
  createDisabledReason,
  error,
  notice,
  metrics,
  buildStateLabel,
  formatDate,
  progress,
  errorCode,
  shortRevision,
  providerLabel,
  shortEndpoint,
  loadData,
  openCreateDialog,
  closeCreateDialog,
  handleCreateBuild,
  openReleasePreview,
  closeReleaseDialog,
  handlePublishRelease,
  openReleaseDetail,
  closeReleaseDetail,
  openRollbackDialog,
  closeRollbackDialog,
  handleRollbackRelease,
} = useBuildsPage()
</script>

<template>
  <section class="page-section builds-page">
    <div class="page-intro">
      <div>
        <p class="eyebrow">
          索引生命周期
        </p>
        <h1>构建与发布</h1>
        <p class="page-description">
          冻结当前文档版本与处理配置，生成可校验、可发布的知识库索引。
        </p>
      </div>
      <div class="build-page-actions">
        <button class="secondary-button" type="button" :disabled="loading" @click="loadData()">
          <RefreshCw :size="15" aria-hidden="true" />刷新
        </button>
        <div class="build-create-action">
          <button
            class="primary-button"
            type="button"
            :disabled="creating || Boolean(createDisabledReason)"
            :title="createDisabledReason || '选择目标知识库并创建构建'"
            @click="openCreateDialog"
          >
            <DatabaseZap :size="15" aria-hidden="true" />{{ creating ? '正在创建…' : '创建构建' }}
          </button>
          <small v-if="createDisabledReason">{{ createDisabledReason }}</small>
        </div>
      </div>
    </div>

    <div v-if="error" class="error-banner">
      {{ error }}
    </div>
    <div v-if="notice" class="success-banner">
      {{ notice }}
    </div>

    <div class="build-context content-card">
      <label>
        <span>筛选知识库</span>
        <select v-model="knowledgeBaseId">
          <option value="all">全部知识库</option>
          <option v-for="knowledgeBase in knowledgeBases" :key="knowledgeBase.id" :value="knowledgeBase.id">
            {{ knowledgeBase.name }}
          </option>
        </select>
      </label>
      <p v-if="selectedKnowledgeBase">
        当前筛选“{{ selectedKnowledgeBase.name }}”；创建构建时将默认选择该知识库。
      </p>
      <p v-else>
        当前显示全部知识库的构建记录；点击“创建构建”可选择目标知识库。
      </p>
    </div>

    <div class="build-metrics">
      <article v-for="metric in metrics" :key="metric.label" class="build-metric content-card" :class="metric.tone">
        <span>{{ metric.label }}</span>
        <strong>{{ metric.value }}</strong>
        <small>{{ metric.hint }}</small>
      </article>
    </div>

    <div v-if="loading" class="content-card module-placeholder build-loading">
      <span class="loading-spinner" />
      <p>正在加载构建记录…</p>
    </div>

    <div v-else class="content-card table-card build-table-card">
      <table>
        <thead>
          <tr>
            <th>构建</th><th>发布状态</th><th>知识库</th><th>构建状态</th><th>向量进度</th><th>嵌入模型 / 接入配置</th><th>操作</th>
          </tr>
        </thead>
        <tbody v-if="visibleBuilds.length">
          <tr v-for="build in visibleBuilds" :key="build.id">
            <td>
              <div class="build-name">
                <span class="build-icon" :class="build.state">
                  <CheckCircle2 v-if="build.state === 'ready'" :size="14" />
                  <TriangleAlert v-else-if="build.state === 'failed'" :size="14" />
                  <Box v-else :size="14" />
                </span>
                <div>
                  <strong>构建 #{{ build.id }}</strong>
                  <small>任务 #{{ build.task_id }} · {{ formatDate(build.updated_at) }}</small>
                </div>
              </div>
            </td>
            <td>
              <span v-if="build.is_active_release" class="status-pill ready">当前 Release #{{ build.release_id }}</span>
              <span v-else-if="build.release_id" class="status-pill retired">历史 Release #{{ build.release_id }}</span>
              <span v-else class="status-pill draft">未发布</span>
            </td>
            <td>
              <div class="build-context-cell">
                <strong>{{ build.knowledge_base_name }}</strong><small>Epoch {{ build.input_epoch }}</small>
              </div>
            </td>
            <td>
              <span class="status-pill" :class="build.state">{{ buildStateLabel(build.state) }}</span>
              <small v-if="build.state !== 'failed'" class="build-count">{{ build.completed_documents }} / {{ build.document_count }} 份文档</small>
              <small v-if="build.state === 'failed'" class="build-error">{{ errorCode(build) }}</small>
            </td>
            <td>
              <div class="build-progress">
                <div><span :style="{ width: `${progress(build)}%` }" /></div>
                <small>{{ build.embedded_count }} / {{ build.chunk_count }} · {{ progress(build) }}%</small>
              </div>
            </td>
            <td>
              <div class="model-cell">
                <Cpu :size="13" />
                <span>{{ build.model_name }}</span>
                <small>{{ build.dimension }} 维 · {{ shortRevision(build.model_revision) }}</small>
                <small>Profile #{{ build.embedding_profile_id }} · {{ providerLabel(build.provider) }}</small>
                <small>{{ shortEndpoint(build.base_url) }} · {{ shortRevision(build.embedding_definition_hash) }}</small>
              </div>
            </td>
            <td>
              <button
                class="table-action-button"
                type="button"
                :disabled="build.state !== 'ready' || Boolean(build.release_id)"
                @click="openReleasePreview(build)"
              >
                <Rocket :size="13" aria-hidden="true" />{{ build.release_id ? '已发布' : '发布' }}
              </button>
            </td>
          </tr>
        </tbody>
        <tbody v-else>
          <tr>
            <td colspan="7">
              <div class="empty-state compact">
                <div class="empty-icon">
                  <DatabaseZap :size="18" />
                </div>
                <strong>暂无构建</strong>
                <span>选择知识库并创建第一个索引构建。</span>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <ReleaseHistory
      :releases="releases"
      :loading="loading"
      :selected-knowledge-base-name="selectedKnowledgeBase?.name ?? ''"
      @view="openReleaseDetail"
      @rollback="openRollbackDialog"
    />

    <CreateBuildDialog
      :open="createDialogOpen"
      :knowledge-bases="knowledgeBases"
      :initial-knowledge-base-id="initialCreateKnowledgeBaseId"
      :creating="creating"
      @close="closeCreateDialog"
      @confirm="handleCreateBuild"
    />
    <ReleaseDiffDialog
      :open="releaseDialogOpen"
      :loading="previewingRelease"
      :publishing="publishingRelease"
      :preview="releasePreview"
      @close="closeReleaseDialog"
      @publish="handlePublishRelease"
    />
    <ReleaseDetailDialog
      :open="releaseDetailOpen"
      :loading="loadingReleaseDetail"
      :error="releaseDetailError"
      :release="selectedRelease"
      :detail="releaseBuildDetail"
      @close="closeReleaseDetail"
    />
    <ReleaseRollbackDialog
      :open="rollbackDialogOpen"
      :rolling-back="rollingBack"
      :target-release="rollbackTarget"
      :current-release="currentRelease"
      @close="closeRollbackDialog"
      @confirm="handleRollbackRelease"
    />
  </section>
</template>
