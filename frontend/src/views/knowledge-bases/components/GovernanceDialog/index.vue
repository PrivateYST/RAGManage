<!-- 知识库治理编辑：集中维护影响检索准入与引用展示的业务元数据。 -->
<script setup lang="ts">
import type { KnowledgeBaseForm } from '../../type'
import type { SpaceMember } from '@/api/members'
import { reactive, watch } from 'vue'
const props = defineProps<{ form: KnowledgeBaseForm; members: SpaceMember[]; saving: boolean; name: string }>()
const emit = defineEmits<{ cancel: []; submit: [value: KnowledgeBaseForm] }>()
const draft = reactive<KnowledgeBaseForm>({ ...props.form })
watch(() => props.form, (value) => Object.assign(draft, value), { deep: true })
</script>
<template>
  <form class="dialog-card" @submit.prevent="emit('submit', { ...draft })">
    <div class="dialog-heading"><div><p class="eyebrow">知识库治理</p><h2>{{ props.name }}</h2></div><button type="button" class="dialog-close" @click="emit('cancel')">关闭</button></div>
    <label>业务场景<input v-model.trim="draft.business_scenario" maxlength="240" /></label>
    <label>目标用户<input v-model.trim="draft.target_users" maxlength="240" /></label>
    <label>负责人<select v-model="draft.owner_user_id"><option value="">未指定</option><option v-for="member in props.members" :key="member.id" :value="member.id">{{ member.display_name || member.login }}</option></select></label>
    <label>来源系统<input v-model.trim="draft.source_system" maxlength="160" /></label>
    <label>可信等级<select v-model="draft.trust_level"><option value="high">高</option><option value="medium">中</option><option value="low">低</option></select></label>
    <div class="grid grid-cols-2 gap-[10px]"><label>有效期起始<input v-model="draft.valid_from" type="date" /></label><label>有效期截止<input v-model="draft.valid_until" type="date" /></label></div>
    <label>业务标签<input v-model.trim="draft.business_tags" maxlength="1200" placeholder="多个标签用逗号分隔" /></label>
    <div class="dialog-actions"><button type="button" class="secondary-button" @click="emit('cancel')">取消</button><button class="primary-button" :disabled="props.saving">{{ props.saving ? '保存中…' : '保存治理信息' }}</button></div>
  </form>
</template>
