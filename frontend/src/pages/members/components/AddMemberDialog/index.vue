<script setup lang="ts">
import type { AddMemberDialogEmits, AddMemberDialogProps } from './type'
import { X } from 'lucide-vue-next'
import { assignableSpaceRoles, useAddMemberDialog } from './index'
import './index.scss'

defineProps<AddMemberDialogProps>()
const emit = defineEmits<AddMemberDialogEmits>()
const { login, roleCode, submitting, close, submit } = useAddMemberDialog(emit)
</script>

<template>
  <div v-if="open" class="dialog-backdrop" @click.self="close">
    <form class="dialog-card member-add-dialog" aria-labelledby="add-member-title" @submit.prevent="submit">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">
            当前空间
          </p><h2 id="add-member-title">
            添加成员
          </h2>
        </div>
        <button class="dialog-close" type="button" aria-label="关闭" :disabled="submitting" @click="close">
          <X :size="16" />
        </button>
      </div>
      <p class="member-dialog-hint">
        账号需要先由平台管理员创建。输入准确登录名后，将其加入当前空间。
      </p>
      <label>登录名<input v-model.trim="login" required minlength="3" maxlength="120" autocomplete="off" placeholder="例如 zhangsan"></label>
      <label>空间角色<select v-model="roleCode"><option v-for="[value, label] in assignableSpaceRoles" :key="value" :value="value">{{ label }}</option></select></label>
      <div class="member-role-help">
        <strong v-if="roleCode === 'space_admin'">可管理当前空间、知识库与成员。</strong>
        <strong v-else-if="roleCode === 'customer_reader'">可查看当前空间内全部已发布知识库并进行问答。</strong>
        <strong v-else>默认无内容权限，需要再分配具体知识库角色。</strong>
      </div>
      <div class="dialog-actions">
        <button class="secondary-button" type="button" :disabled="submitting" @click="close">
          取消
        </button>
        <button class="primary-button" type="submit" :disabled="submitting || !login.trim()">
          {{ submitting ? '添加中…' : '确认添加' }}
        </button>
      </div>
    </form>
  </div>
</template>
