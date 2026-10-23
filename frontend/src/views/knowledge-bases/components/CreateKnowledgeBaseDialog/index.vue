<!-- 创建知识库表单：仅负责字段输入并上报表单值，保存状态由页面控制。 -->
<script setup lang="ts">
import type { KnowledgeBaseForm } from '../../type'
import type { CreateKnowledgeBaseDialogProps } from './type'
import { computed } from 'vue'
import { useCreateKnowledgeBaseDialog } from './index'

const props = defineProps<CreateKnowledgeBaseDialogProps>()
const emit = defineEmits<{
  cancel: []
  submit: [value: KnowledgeBaseForm]
}>()
const dialog = useCreateKnowledgeBaseDialog(props)
const draft = dialog.draft
const saving = computed(() => props.saving)
</script>

<template>
  <form class="dialog-card create-kb-dialog" @submit.prevent="dialog.submit(emit)">
    <div class="dialog-heading">
      <div>
        <p class="eyebrow">知识库管理</p>
        <h2>创建知识库</h2>
      </div>
      <button type="button" class="dialog-close" @click="emit('cancel')">关闭</button>
    </div>
    <div class="dialog-form-body">
      <label>所属空间<input :value="spaceName" disabled /></label>
      <label>
        知识库名称
        <input v-model.trim="draft.name" required minlength="2" maxlength="120" />
      </label>
      <label>
        业务用途
        <select v-model="draft.purpose">
          <option value="general">通用知识</option>
          <option value="product">产品说明</option>
          <option value="troubleshooting">故障排查</option>
          <option value="rule">业务规则</option>
        </select>
      </label>
      <label>
        说明
        <textarea
          v-model.trim="draft.description"
          maxlength="1000"
          rows="3"
          placeholder="说明知识库覆盖的业务范围"
        />
      </label>
      <label
        >业务场景<input
          v-model.trim="draft.business_scenario"
          maxlength="240"
          placeholder="例如：基层公共卫生服务问答"
      /></label>
      <label
        >目标用户<input
          v-model.trim="draft.target_users"
          maxlength="240"
          placeholder="例如：基层医务人员、公共卫生管理员"
      /></label>
      <label
        >来源系统<input
          v-model.trim="draft.source_system"
          maxlength="160"
          placeholder="例如：国家卫健委规范库"
      /></label>
      <label
        >可信等级<select v-model="draft.trust_level">
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
        </select></label
      >
      <div class="grid grid-cols-2 gap-[10px]">
        <label>有效期起始<input v-model="draft.valid_from" type="date" /></label>
        <label>有效期截止<input v-model="draft.valid_until" type="date" /></label>
      </div>
      <label
        >业务标签<input
          v-model.trim="draft.business_tags"
          maxlength="1200"
          placeholder="多个标签用逗号分隔"
      /></label>
    </div>
    <div class="dialog-actions">
      <button type="button" class="secondary-button" @click="emit('cancel')">取消</button>
      <button type="submit" class="primary-button" :disabled="saving">
        {{ saving ? '创建中…' : '创建知识库' }}
      </button>
    </div>
  </form>
</template>

<style scoped src="./index.scss"></style>
