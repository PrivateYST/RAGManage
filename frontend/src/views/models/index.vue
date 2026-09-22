<!-- 模型配置视图只负责 Tab 与领域组件组合；请求和状态转换由同目录逻辑模块维护。 -->
<script setup lang="ts">
import { Activity, AppConfirmDialog, Cpu, KeyRound, Plus, RefreshCw, Settings2 } from '@/components'
import ApiKeyManager from './components/ApiKeyManager/index.vue'
import EmbeddingProfiles from './components/EmbeddingProfiles/index.vue'
import EndpointFormDialog from './components/EndpointFormDialog/index.vue'
import EndpointTable from './components/EndpointTable/index.vue'
import GatewayApiKeyDialog from './components/GatewayApiKeyDialog/index.vue'
import IngestionProfiles from './components/IngestionProfiles/index.vue'
import RuntimeProfiles from './components/RuntimeProfiles/index.vue'
import { useModelsPage } from './index'

const {
  view,
  loading,
  busyId,
  endpointDialogOpen,
  gatewayKeyDialogOpen,
  editingEndpoint,
  pendingEndpoint,
  endpoints,
  activeEndpoints,
  knowledgeBases,
  selectedKnowledgeBaseId,
  profiles,
  lastHealthResult,
  canManageEndpoints,
  loadPage,
  openCreateEndpoint,
  openGatewayKeyDialog,
  handleGatewayKeySaved,
  openEditEndpoint,
  submitEndpoint,
  toggleEndpoint,
  cancelEndpointToggle,
  confirmEndpointToggle,
  runHealthCheck,
  addIngestionProfile,
  addEmbeddingProfile,
  addRuntimeProfile,
  activateRuntime,
} = useModelsPage()
</script>

<template>
  <section class="mx-auto w-full max-w-[1160px] pb-[28px]">
    <div class="page-intro">
      <div>
        <p class="eyebrow">系统配置 / 模型服务</p>
        <h1>模型与运行配置</h1>
        <p class="page-description">
          统一管理全局模型网关、知识库 Profile，以及按医院下发的 Open WebUI 原生 API Key。
        </p>
      </div>
      <div
        class="flex flex-wrap items-center justify-end gap-[8px] max-sm:w-full max-sm:justify-start"
      >
        <button
          v-if="canManageEndpoints"
          class="secondary-button"
          type="button"
          @click="openGatewayKeyDialog"
        >
          <KeyRound :size="14" />配置全局网关 Key
        </button>
        <button
          v-if="view !== 'api-keys'"
          class="secondary-button"
          type="button"
          :disabled="loading"
          @click="loadPage"
        >
          <RefreshCw :size="14" />刷新</button
        ><button
          v-if="canManageEndpoints && view === 'endpoints'"
          class="primary-button"
          type="button"
          @click="openCreateEndpoint"
        >
          <Plus :size="14" />登记端点
        </button>
      </div>
    </div>
    <div
      v-if="lastHealthResult"
      class="mb-[14px] flex items-center gap-[8px] rounded-md border px-[12px] py-[10px] text-xs"
      :class="
        lastHealthResult.result.status === 'healthy'
          ? 'border-status-up/30 bg-status-up-soft text-status-up'
          : 'border-destructive/30 bg-destructive/10 text-destructive'
      "
    >
      <Activity :size="15" aria-hidden="true" />
      <div>
        <strong class="block text-xs"
          >{{ lastHealthResult.endpoint.name }} · {{ lastHealthResult.result.model }}</strong
        ><small
          v-if="lastHealthResult.result.status === 'healthy'"
          class="mt-[2px] block text-[10px]"
          >真实调用成功，耗时 {{ lastHealthResult.result.latency_ms }} ms<span
            v-if="lastHealthResult.result.dimension"
            >，实测 {{ lastHealthResult.result.dimension }} 维</span
          ></small
        ><small v-else>{{ lastHealthResult.result.error }}</small>
      </div>
    </div>

    <nav
      class="mb-[12px] flex items-center gap-[4px] overflow-x-auto rounded-md border border-border bg-secondary p-[4px]"
      aria-label="模型配置视图"
    >
      <button
        v-if="canManageEndpoints"
        type="button"
        class="inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded px-[12px] text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :class="view === 'endpoints' ? 'bg-card font-semibold text-primary' : ''"
        @click="view = 'endpoints'"
      >
        <Cpu :size="14" />模型端点
      </button>
      <button
        type="button"
        class="inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded px-[12px] text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :class="view === 'profiles' ? 'bg-card font-semibold text-primary' : ''"
        @click="view = 'profiles'"
      >
        <Settings2 :size="14" />知识库 Profile
      </button>
      <button
        v-if="canManageEndpoints"
        type="button"
        class="inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded px-[12px] text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :class="view === 'api-keys' ? 'bg-card font-semibold text-primary' : ''"
        @click="view = 'api-keys'"
      >
        <KeyRound :size="14" />医院网关 Key
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

    <template v-else-if="view === 'profiles'">
      <div
        class="mb-[12px] flex min-h-[58px] items-center justify-between gap-[16px] rounded-md border border-primary/20 bg-primary/5 px-[12px] py-[10px] max-sm:items-stretch max-sm:flex-col"
      >
        <div>
          <strong class="block text-[13px] font-semibold text-foreground">配置对象</strong>
          <small class="mt-[2px] block text-[10px] text-muted-foreground"
            >Profile 归属当前空间中的单个知识库，跨空间不可见。</small
          >
        </div>
        <select
          v-model="selectedKnowledgeBaseId"
          class="h-[36px] min-w-[240px] rounded-md border border-primary/20 bg-background px-[10px] text-xs text-foreground outline-none focus:border-primary focus:ring-2 focus:ring-primary/20 max-sm:w-full max-sm:min-w-0"
          aria-label="选择知识库"
        >
          <option v-if="!knowledgeBases.length" value="">当前空间暂无可管理知识库</option>
          <option v-for="kb in knowledgeBases" :key="kb.id" :value="kb.id">
            {{ kb.name }}
          </option>
        </select>
      </div>
      <div v-if="profiles" class="grid gap-[12px] lg:grid-cols-2">
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
      <section
        v-else
        class="content-card grid min-h-[220px] place-content-center justify-items-center gap-[8px] text-xs text-muted-foreground"
      >
        <Settings2 :size="24" /><strong>{{
          selectedKnowledgeBaseId ? '正在加载 Profile…' : '请选择一个知识库'
        }}</strong>
      </section>
    </template>

    <ApiKeyManager v-else-if="canManageEndpoints" @configure="openGatewayKeyDialog" />

    <EndpointFormDialog
      :open="endpointDialogOpen"
      :endpoint="editingEndpoint"
      @close="endpointDialogOpen = false"
      @submit="submitEndpoint"
    />
    <GatewayApiKeyDialog
      :open="gatewayKeyDialogOpen"
      @close="gatewayKeyDialogOpen = false"
      @saved="handleGatewayKeySaved"
    />
    <AppConfirmDialog
      :open="Boolean(pendingEndpoint)"
      :title="pendingEndpoint ? `确认停用“${pendingEndpoint.name}”？` : '确认停用模型端点'"
      description="停用后新的模型请求不会再使用此端点，现有请求不受影响。"
      confirm-label="确认停用"
      :busy="Boolean(pendingEndpoint && busyId === `endpoint-${pendingEndpoint.id}`)"
      @update:open="(open) => !open && cancelEndpointToggle()"
      @confirm="confirmEndpointToggle"
    />
  </section>
</template>
