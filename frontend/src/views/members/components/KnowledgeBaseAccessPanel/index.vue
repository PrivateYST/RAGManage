<script setup lang="ts">
import type { KnowledgeBaseAccessPanelEmits, KnowledgeBaseAccessPanelProps } from './type'
import type { KnowledgeBaseRoleCode } from '@/api/members'
import type { AppTableColumn } from '@/components'
import { AppTable, KeyRound, Library, ShieldCheck } from '@/components'
import { knowledgeBaseRoleOptions, useKnowledgeBaseAccessPanel } from './index'
import './index.scss'

const props = defineProps<KnowledgeBaseAccessPanelProps>()
const emit = defineEmits<KnowledgeBaseAccessPanelEmits>()
const { candidateId, roleCode, availableCandidates, selectedCandidate, submitGrant } =
  useKnowledgeBaseAccessPanel(props, emit)
const columns: AppTableColumn<import('@/api/members').KnowledgeBaseMember>[] = [
  { key: 'member', title: '成员' },
  { key: 'role', title: '知识库角色' },
  { key: 'status', title: '状态' },
  { key: 'actions', title: '操作' },
]
</script>

<template>
  <section class="kb-access-panel">
    <div class="kb-access-toolbar">
      <div>
        <span class="kb-access-icon"><Library :size="16" /></span>
        <div>
          <strong>知识库授权</strong
          ><small>内部空间成员只有获得显式授权后才能访问对应知识库。</small>
        </div>
      </div>
      <label>
        <span>选择知识库</span>
        <select
          :value="selectedKnowledgeBaseId"
          @change="
            emit('update:selectedKnowledgeBaseId', ($event.target as HTMLSelectElement).value)
          "
        >
          <option v-if="knowledgeBases.length === 0" value="">暂无可管理知识库</option>
          <option v-for="item in knowledgeBases" :key="item.id" :value="item.id">
            {{ item.name }}
          </option>
        </select>
      </label>
    </div>

    <form class="kb-grant-form" @submit.prevent="submitGrant">
      <label
        ><span>空间成员</span
        ><select v-model="candidateId" required>
          <option value="">选择待授权成员</option>
          <option v-for="item in availableCandidates" :key="item.id" :value="item.id">
            {{ item.display_name }}（{{ item.login }}）{{
              item.grant_status === 'disabled' ? ' · 已撤销' : ''
            }}
          </option>
        </select></label
      >
      <label
        ><span>知识库角色</span
        ><select v-model="roleCode">
          <option v-for="[value, label] in knowledgeBaseRoleOptions" :key="value" :value="value">
            {{ label }}
          </option>
        </select></label
      >
      <button
        class="primary-button"
        type="submit"
        :disabled="!selectedKnowledgeBaseId || !candidateId || Boolean(busyId)"
      >
        <KeyRound :size="14" />{{
          selectedCandidate?.grant_status === 'disabled' ? '恢复授权' : '添加授权'
        }}
      </button>
    </form>

    <div v-if="loading" class="kb-access-state">
      <span class="loading-spinner" /><strong>正在加载授权…</strong>
    </div>
    <div v-else-if="!selectedKnowledgeBaseId" class="kb-access-state">
      <Library :size="24" /><strong>暂无可管理知识库</strong>
    </div>
    <div v-else-if="members.length === 0" class="kb-access-state">
      <ShieldCheck :size="24" /><strong>当前没有显式知识库授权</strong
      ><span>空间管理员仍拥有管理权限，客户用户按空间读取已发布内容。</span>
    </div>
    <div v-else class="kb-access-table-wrap">
      <AppTable :rows="members" :columns="columns" row-key="id" class="kb-access-table">
        <template #cell-member="{ row: member }">
          <strong>{{ member.display_name }}</strong
          ><small>{{ member.login }}</small>
        </template>
        <template #cell-role="{ row: member }">
          <select
            :value="member.role_code"
            :disabled="busyId === `grant-${member.id}` || member.status === 'disabled'"
            :aria-label="`修改 ${member.display_name} 的知识库角色`"
            @change="
              emit(
                'changeRole',
                member,
                ($event.target as HTMLSelectElement).value as KnowledgeBaseRoleCode,
              )
            "
          >
            <option v-for="[value, label] in knowledgeBaseRoleOptions" :key="value" :value="value">
              {{ label }}
            </option>
          </select>
        </template>
        <template #cell-status="{ row: member }">
          <span class="status-pill" :class="member.status === 'active' ? 'ready' : 'disabled'">{{
            member.status === 'active' ? '有效' : '已撤销'
          }}</span>
        </template>
        <template #cell-actions="{ row: member }">
          <button
            class="member-row-action"
            :class="{ danger: member.status === 'active' }"
            type="button"
            :disabled="busyId === `grant-${member.id}`"
            @click="emit('toggleStatus', member)"
          >
            {{ member.status === 'active' ? '撤销' : '恢复' }}
          </button>
        </template>
      </AppTable>
    </div>
  </section>
</template>
