<script setup lang="ts">
import type { MemberTableEmits, MemberTableProps } from './type'
import { UserRoundX, Users } from 'lucide-vue-next'
import { formatJoinDate, spaceRoleOptions } from './index'
import './index.scss'

defineProps<MemberTableProps>()
const emit = defineEmits<MemberTableEmits>()
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
      <table class="member-table">
        <thead>
          <tr><th>成员</th><th>空间角色</th><th>知识库授权</th><th>状态</th><th>加入日期</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="member in items" :key="member.id">
            <td>
              <div class="member-identity">
                <span>{{ member.display_name.slice(0, 1) }}</span>
                <div><strong>{{ member.display_name }}</strong><small>{{ member.login }}</small></div>
              </div>
            </td>
            <td>
              <select
                class="member-role-select"
                :value="member.role_code"
                :disabled="busyId === `space-${member.id}` || member.status === 'disabled'"
                :aria-label="`修改 ${member.display_name} 的空间角色`"
                @change="emit('changeRole', member, ($event.target as HTMLSelectElement).value as import('../../../../api/members').SpaceRoleCode)"
              >
                <option v-for="[value, label] in spaceRoleOptions" :key="value" :value="value">
                  {{ label }}
                </option>
              </select>
            </td>
            <td><strong class="member-grant-count">{{ member.knowledge_base_count }}</strong> 个显式授权</td>
            <td><span class="status-pill" :class="member.status === 'active' ? 'ready' : 'disabled'">{{ member.status === 'active' ? '有效' : '已停用' }}</span></td>
            <td>{{ formatJoinDate(member.created_at) }}</td>
            <td>
              <button
                class="member-row-action"
                :class="{ danger: member.status === 'active' }"
                type="button"
                :disabled="busyId === `space-${member.id}`"
                @click="emit('toggleStatus', member)"
              >
                <UserRoundX :size="14" />{{ member.status === 'active' ? '停用' : '恢复' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
