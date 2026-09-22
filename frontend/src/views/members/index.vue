<!-- 成员与授权工作区：编排空间成员、知识库授权及破坏性状态变更确认。 -->
<script setup lang="ts">
import {
  AppConfirmDialog,
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
  addDialogOpen,
  spaceMembers,
  knowledgeBases,
  knowledgeBaseMembers,
  candidates,
  auditItems,
  selectedKnowledgeBaseId,
  pendingStatus,
  canManageSpace,
  stats,
  loadPage,
  submitSpaceMember,
  changeSpaceRole,
  toggleSpaceStatus,
  submitKnowledgeBaseGrant,
  changeKnowledgeBaseRole,
  toggleKnowledgeBaseStatus,
  cancelPendingStatus,
  confirmPendingStatus,
} = useMembersPage()
</script>

<template>
  <section class="mx-auto w-full max-w-[1160px] pb-[28px]">
    <div class="page-intro">
      <div>
        <p class="eyebrow">客户空间</p>
        <h1>成员与权限</h1>
        <p class="page-description">
          管理当前空间的成员身份、知识库角色与授权历史。平台身份不会自动获得客户资料权限。
        </p>
      </div>
      <div class="flex items-center gap-[8px] max-sm:w-full max-sm:justify-end">
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

    <div
      class="mb-[14px] flex min-h-[42px] items-center gap-[8px] rounded-md border border-primary/20 bg-primary/5 px-[14px] text-[11px] text-primary max-sm:flex-wrap"
    >
      <ShieldCheck :size="15" aria-hidden="true" /><span
        >当前空间：<strong class="text-xs text-foreground">{{
          auth.activeSpace?.name || '未选择空间'
        }}</strong></span
      >
      <span class="ml-auto rounded bg-primary/10 px-[8px] py-[2px] text-[10px] text-primary">{{
        canManageSpace ? '空间管理员' : '知识库管理员'
      }}</span>
    </div>

    <div v-if="canManageSpace" class="mb-[16px] grid grid-cols-2 gap-[10px] lg:grid-cols-4">
      <article
        class="flex min-h-[72px] items-center gap-[10px] rounded-lg border border-border bg-card px-[14px] py-[12px]"
      >
        <span
          class="grid size-[32px] shrink-0 place-items-center rounded-md bg-primary/10 text-primary"
          ><Users :size="15"
        /></span>
        <div>
          <small class="text-[9px] text-muted-foreground">有效成员</small
          ><strong class="text-lg leading-tight">{{ stats.active }}</strong>
        </div>
      </article>
      <article
        class="flex min-h-[72px] items-center gap-[10px] rounded-lg border border-border bg-card px-[14px] py-[12px]"
      >
        <span
          class="grid size-[32px] shrink-0 place-items-center rounded-md bg-primary/10 text-primary"
          ><ShieldCheck :size="15"
        /></span>
        <div>
          <small class="text-[9px] text-muted-foreground">空间管理员</small
          ><strong class="text-lg leading-tight">{{ stats.admins }}</strong>
        </div>
      </article>
      <article
        class="flex min-h-[72px] items-center gap-[10px] rounded-lg border border-border bg-card px-[14px] py-[12px]"
      >
        <span
          class="grid size-[32px] shrink-0 place-items-center rounded-md bg-primary/10 text-primary"
          ><UserRoundCheck :size="15"
        /></span>
        <div>
          <small class="text-[9px] text-muted-foreground">客户用户</small
          ><strong class="text-lg leading-tight">{{ stats.customers }}</strong>
        </div>
      </article>
      <article
        class="flex min-h-[72px] items-center gap-[10px] rounded-lg border border-border bg-card px-[14px] py-[12px]"
      >
        <span
          class="grid size-[32px] shrink-0 place-items-center rounded-md bg-primary/10 text-primary"
          ><KeyRound :size="15"
        /></span>
        <div>
          <small class="text-[9px] text-muted-foreground">知识库授权</small
          ><strong class="text-lg leading-tight">{{ stats.grants }}</strong>
        </div>
      </article>
    </div>

    <nav
      class="mb-[10px] flex items-center gap-[4px] overflow-x-auto rounded-md border border-border bg-secondary p-[4px]"
      aria-label="成员管理视图"
    >
      <button
        v-if="canManageSpace"
        type="button"
        class="inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded px-[12px] text-[11px] text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :class="view === 'space' ? 'bg-card font-semibold text-primary' : ''"
        @click="view = 'space'"
      >
        <Users :size="14" />空间成员
      </button>
      <button
        type="button"
        class="inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded px-[12px] text-[11px] text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :class="view === 'knowledge' ? 'bg-card font-semibold text-primary' : ''"
        @click="view = 'knowledge'"
      >
        <KeyRound :size="14" />知识库授权
      </button>
      <button
        v-if="canManageSpace"
        type="button"
        class="inline-flex h-[32px] shrink-0 items-center gap-[6px] rounded px-[12px] text-[11px] text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        :class="view === 'audit' ? 'bg-card font-semibold text-primary' : ''"
        @click="view = 'audit'"
      >
        <History :size="14" />授权历史
      </button>
    </nav>

    <section v-if="view === 'space' && canManageSpace" class="content-card overflow-hidden p-0">
      <header
        class="flex min-h-[62px] items-center justify-between gap-[16px] border-b border-border px-[18px] py-[12px]"
      >
        <div>
          <strong class="block text-[13px] font-semibold">空间成员</strong>
          <small class="mt-[2px] block text-[10px] text-muted-foreground"
            >停用成员后，其当前会话中的所有空间与知识库访问会立即失效。</small
          >
        </div>
        <span class="text-[10px] text-muted-foreground">共 {{ spaceMembers.length }} 人</span>
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
    <AppConfirmDialog
      :open="Boolean(pendingStatus)"
      :title="
        pendingStatus?.kind === 'space'
          ? `确认停用“${pendingStatus.member.display_name}”？`
          : pendingStatus
            ? `确认撤销“${pendingStatus.member.display_name}”的知识库授权？`
            : '确认变更成员状态'
      "
      :description="
        pendingStatus?.kind === 'space'
          ? '停用后该成员当前会话中的空间与知识库访问会立即失效。'
          : '撤销后该成员将无法访问当前知识库，历史审计记录仍会保留。'
      "
      :confirm-label="pendingStatus?.kind === 'space' ? '确认停用' : '确认撤销授权'"
      :busy="Boolean(pendingStatus && busyId === pendingStatus.busyId)"
      @update:open="(open) => !open && cancelPendingStatus()"
      @confirm="confirmPendingStatus"
    />
  </section>
</template>
