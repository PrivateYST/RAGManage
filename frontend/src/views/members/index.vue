<script setup lang="ts">
import {
  History,
  KeyRound,
  Plus,
  RefreshCw,
  ShieldCheck,
  UserRoundCheck,
  Users,
} from '@/components'
import AddMemberDialog from './components/AddMemberDialog/index.vue'
import AuditHistory from './components/AuditHistory/index.vue'
import KnowledgeBaseAccessPanel from './components/KnowledgeBaseAccessPanel/index.vue'
import MemberTable from './components/MemberTable/index.vue'
import { useMembersPage } from './index'
import './index.scss'

const {
  auth,
  view,
  loading,
  grantLoading,
  busyId,
  error,
  success,
  addDialogOpen,
  spaceMembers,
  knowledgeBases,
  knowledgeBaseMembers,
  candidates,
  auditItems,
  selectedKnowledgeBaseId,
  canManageSpace,
  stats,
  loadPage,
  submitSpaceMember,
  changeSpaceRole,
  toggleSpaceStatus,
  submitKnowledgeBaseGrant,
  changeKnowledgeBaseRole,
  toggleKnowledgeBaseStatus,
} = useMembersPage()
</script>

<template>
  <section class="page-section members-page">
    <div class="page-intro">
      <div>
        <p class="eyebrow">客户空间</p>
        <h1>成员与权限</h1>
        <p class="page-description">
          管理当前空间的成员身份、知识库角色与授权历史。平台身份不会自动获得客户资料权限。
        </p>
      </div>
      <div class="member-page-actions">
        <button class="secondary-button" type="button" :disabled="loading" @click="loadPage">
          <RefreshCw :size="14" />刷新
        </button>
        <button
          v-if="canManageSpace"
          class="primary-button"
          type="button"
          @click="addDialogOpen = true"
        >
          <Plus :size="14" />添加成员
        </button>
      </div>
    </div>

    <div v-if="error" class="error-banner" role="alert">
      {{ error }}
    </div>
    <div v-if="success" class="member-success-banner" role="status">
      {{ success }}
    </div>

    <div class="member-context-bar">
      <ShieldCheck :size="15" /><span
        >当前空间：<strong>{{ auth.activeSpace?.name || '未选择空间' }}</strong></span
      ><span class="member-context-role">{{ canManageSpace ? '空间管理员' : '知识库管理员' }}</span>
    </div>

    <div v-if="canManageSpace" class="member-stats-grid">
      <article>
        <span><Users :size="15" /></span>
        <div>
          <small>有效成员</small><strong>{{ stats.active }}</strong>
        </div>
      </article>
      <article>
        <span><ShieldCheck :size="15" /></span>
        <div>
          <small>空间管理员</small><strong>{{ stats.admins }}</strong>
        </div>
      </article>
      <article>
        <span><UserRoundCheck :size="15" /></span>
        <div>
          <small>客户用户</small><strong>{{ stats.customers }}</strong>
        </div>
      </article>
      <article>
        <span><KeyRound :size="15" /></span>
        <div>
          <small>知识库授权</small><strong>{{ stats.grants }}</strong>
        </div>
      </article>
    </div>

    <nav class="member-tabs" aria-label="成员管理视图">
      <button
        v-if="canManageSpace"
        type="button"
        :class="{ active: view === 'space' }"
        @click="view = 'space'"
      >
        <Users :size="14" />空间成员
      </button>
      <button type="button" :class="{ active: view === 'knowledge' }" @click="view = 'knowledge'">
        <KeyRound :size="14" />知识库授权
      </button>
      <button
        v-if="canManageSpace"
        type="button"
        :class="{ active: view === 'audit' }"
        @click="view = 'audit'"
      >
        <History :size="14" />授权历史
      </button>
    </nav>

    <section v-if="view === 'space' && canManageSpace" class="content-card member-list-card">
      <header>
        <div>
          <strong>空间成员</strong
          ><small>停用成员后，其当前会话中的所有空间与知识库访问会立即失效。</small>
        </div>
        <span>共 {{ spaceMembers.length }} 人</span>
      </header>
      <MemberTable
        :items="spaceMembers"
        :loading="loading"
        :busy-id="busyId"
        @change-role="changeSpaceRole"
        @toggle-status="toggleSpaceStatus"
      />
    </section>

    <KnowledgeBaseAccessPanel
      v-else-if="view === 'knowledge'"
      v-model:selected-knowledge-base-id="selectedKnowledgeBaseId"
      :knowledge-bases="knowledgeBases"
      :members="knowledgeBaseMembers"
      :candidates="candidates"
      :loading="grantLoading"
      :busy-id="busyId"
      @add-grant="submitKnowledgeBaseGrant"
      @change-role="changeKnowledgeBaseRole"
      @toggle-status="toggleKnowledgeBaseStatus"
    />

    <AuditHistory
      v-else-if="view === 'audit' && canManageSpace"
      :items="auditItems"
      :loading="loading"
    />

    <AddMemberDialog
      :open="addDialogOpen"
      @close="addDialogOpen = false"
      @submit="submitSpaceMember"
    />
  </section>
</template>
