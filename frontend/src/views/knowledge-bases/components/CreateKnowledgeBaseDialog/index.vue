<!-- 创建知识库表单：仅负责字段输入并上报表单值，保存状态由页面控制。 -->
<script setup lang="ts">
import type { KnowledgeBaseForm } from '../../type'
import type { CreateKnowledgeBaseDialogProps } from './type'
import { computed } from 'vue'
import { useCreateKnowledgeBaseDialog } from './index'
import './index.scss'

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
  <form class="dialog-card" @submit.prevent="dialog.submit(emit)">
    <div class="dialog-heading">
      <div>
        <p class="eyebrow">知识库管理</p>
        <h2>创建知识库</h2>
      </div>
      <button type="button" class="dialog-close" @click="emit('cancel')">关闭</button>
    </div>
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
        rows="4"
        placeholder="说明知识库覆盖的业务范围"
      />
    </label>
    <div class="dialog-actions">
      <button type="button" class="secondary-button" @click="emit('cancel')">取消</button>
      <button class="primary-button" :disabled="saving">
        {{ saving ? '创建中…' : '创建知识库' }}
      </button>
    </div>
  </form>
</template>
