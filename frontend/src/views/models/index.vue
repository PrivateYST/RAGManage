<script setup lang="ts">
import { Activity, Cpu, Plus, RefreshCw, Settings2 } from '@/components'
import EmbeddingProfiles from './components/EmbeddingProfiles/index.vue'
import EndpointFormDialog from './components/EndpointFormDialog/index.vue'
import EndpointTable from './components/EndpointTable/index.vue'
import IngestionProfiles from './components/IngestionProfiles/index.vue'
import RuntimeProfiles from './components/RuntimeProfiles/index.vue'
import { useModelsPage } from './index'
import './index.scss'

const {
  view,
  loading,
  busyId,
  error,
  success,
  endpointDialogOpen,
  editingEndpoint,
  endpoints,
  activeEndpoints,
  knowledgeBases,
  selectedKnowledgeBaseId,
  profiles,
  lastHealthResult,
  canManageEndpoints,
  loadPage,
  openCreateEndpoint,
  openEditEndpoint,
  submitEndpoint,
  toggleEndpoint,
  runHealthCheck,
  addIngestionProfile,
  addEmbeddingProfile,
  addRuntimeProfile,
  activateRuntime,
} = useModelsPage()
</script>

<template>
  <section class="page-section models-page">
    <div class="page-intro">
      <div>
        <p class="eyebrow">
          系统配置 / 模型服务
        </p>
        <h1>模型与运行配置</h1>
        <p class="page-description">
          统一管理网关端点、模型白名单、真实连通性检查和知识库不可变 Profile。
        </p>
      </div>
      <div class="model-page-actions">
        <button class="secondary-button" type="button" :disabled="loading" @click="loadPage">
          <RefreshCw :size="14" />刷新
        </button><button
          v-if="canManageEndpoints && view === 'endpoints'"
          class="primary-button"
          type="button"
          @click="openCreateEndpoint"
        >
          <Plus :size="14" />登记端点
        </button>
      </div>
    </div>
    <div v-if="error" class="error-banner" role="alert">
      {{ error }}
    </div>
    <div v-if="success" class="model-success" role="status">
      {{ success }}
    </div>
    <div v-if="lastHealthResult" class="health-result-card" :class="lastHealthResult.result.status">
      <Activity :size="15" />
      <div>
        <strong>{{ lastHealthResult.endpoint.name }} · {{ lastHealthResult.result.model }}</strong><small v-if="lastHealthResult.result.status === 'healthy'">真实调用成功，耗时 {{ lastHealthResult.result.latency_ms }} ms<span
          v-if="lastHealthResult.result.dimension"
        >，实测 {{ lastHealthResult.result.dimension }} 维</span></small><small v-else>{{ lastHealthResult.result.error }}</small>
      </div>
    </div>

    <nav class="model-tabs" aria-label="模型配置视图">
      <button
        v-if="canManageEndpoints"
        type="button"
        :class="{ active: view === 'endpoints' }"
        @click="view = 'endpoints'"
      >
        <Cpu :size="14" />模型端点
      </button>
      <button type="button" :class="{ active: view === 'profiles' }" @click="view = 'profiles'">
        <Settings2 :size="14" />知识库 Profile
      </button>
    </nav>

    <EndpointTable
      v-if="view === 'endpoints' && canManageEndpoints"
      :items="endpoints"
      :loading="loading"
      :busy-id="busyId"
      @edit="openEditEndpoint"
      @toggle="toggleEndpoint"
      @check="runHealthCheck"
    />

    <template v-else>
      <div class="profile-context">
        <div>
          <strong>配置对象</strong><small>Profile 归属当前空间中的单个知识库，跨空间不可见。</small>
        </div>
        <select v-model="selectedKnowledgeBaseId" aria-label="选择知识库">
          <option v-if="!knowledgeBases.length" value="">
            当前空间暂无可管理知识库
          </option>
          <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
            {{ kb.name }}
          </option>
        </select>
      </div>
      <div v-if="profiles" class="profile-grid">
        <IngestionProfiles :items="profiles.ingestion_profiles" @create="addIngestionProfile" />
        <EmbeddingProfiles
          :items="profiles.embedding_profiles"
          :endpoints="activeEndpoints"
          @create="addEmbeddingProfile"
        />
        <RuntimeProfiles
          :items="profiles.runtime_profiles"
          :embedding-profiles="profiles.embedding_profiles"
          :endpoints="activeEndpoints"
          :busy-id="busyId"
          @create="addRuntimeProfile"
          @activate="activateRuntime"
        />
      </div>
      <section v-else class="content-card model-empty-state">
        <Settings2 :size="24" /><strong>{{
          selectedKnowledgeBaseId ? '正在加载 Profile…' : '请选择一个知识库'
        }}</strong>
      </section>
    </template>

    <EndpointFormDialog
      :open="endpointDialogOpen"
      :endpoint="editingEndpoint"
      @close="endpointDialogOpen = false"
      @submit="submitEndpoint"
    />
  </section>
</template>
