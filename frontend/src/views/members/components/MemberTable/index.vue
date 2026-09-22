<script setup lang="ts">
import type { MemberTableEmits, MemberTableProps } from './type'
import type { AppTableColumn } from '@/components'
import { AppTable, UserRoundX, Users } from '@/components'
import { formatJoinDate, spaceRoleOptions } from './index'
import './index.scss'

defineProps<MemberTableProps>()
const emit = defineEmits<MemberTableEmits>()
const columns: AppTableColumn<import('@/api/members').SpaceMember>[] = [
  { key: 'member', title: '成员' },
  { key: 'role', title: '空间角色' },
  { key: 'grants', title: '知识库授权' },
  { key: 'status', title: '状态' },
  { key: 'joined', title: '加入日期' },
  { key: 'actions', title: '操作' },
]
</script>

<template>
  <div class="member-table-wrap">
    <div v-if="loading" class="member-state">
      <span class="loading-spinner" />
      <strong>正在加载空间成员…</strong>
    </div>
    <div v-else-if="items.length === 0" class="member-state">
      <Users :size="24" />
      <strong>当前空间暂无成员</strong>
      <span>使用右上角“添加成员”分配第一个账号。</span>
    </div>
    <div v-else class="member-table-scroll">
      <AppTable :rows="items" :columns="columns" row-key="id" class="member-table">
        <template #cell-member="{ row: member }">
          <div class="member-identity">
            <span>{{ member.display_name.slice(0, 1) }}</span>
            <div>
              <strong>{{ member.display_name }}</strong
              ><small>{{ member.login }}</small>
            </div>
          </div>
        </template>
        <template #cell-role="{ row: member }">
          <select
            class="member-role-select"
            :value="member.role_code"
            :disabled="busyId === `space-${member.id}` || member.status === 'disabled'"
            :aria-label="`修改 ${member.display_name} 的空间角色`"
            @change="
              emit(
                'changeRole',
                member,
                ($event.target as HTMLSelectElement).value as import('@/api/members').SpaceRoleCode,
              )
            "
          >
            <option v-for="[value, label] in spaceRoleOptions" :key="value" :value="value">
              {{ label }}
            </option>
          </select>
        </template>
        <template #cell-grants="{ row: member }">
          <strong class="member-grant-count">{{ member.knowledge_base_count }}</strong>
          个显式授权
        </template>
        <template #cell-status="{ row: member }">
          <span class="status-pill" :class="member.status === 'active' ? 'ready' : 'disabled'">{{
            member.status === 'active' ? '有效' : '已停用'
          }}</span>
        </template>
        <template #cell-joined="{ row: member }">{{ formatJoinDate(member.created_at) }}</template>
        <template #cell-actions="{ row: member }">
          <button
            class="member-row-action"
            :class="{ danger: member.status === 'active' }"
            type="button"
            :disabled="busyId === `space-${member.id}`"
            @click="emit('toggleStatus', member)"
          >
            <UserRoundX :size="14" />{{ member.status === 'active' ? '停用' : '恢复' }}
          </button>
        </template>
      </AppTable>
    </div>
  </div>
</template>
