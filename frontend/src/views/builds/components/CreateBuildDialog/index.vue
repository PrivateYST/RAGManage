<script setup lang="ts">
import type { CreateBuildDialogProps } from './type'
import { DatabaseZap, X } from '@/components'
import { useCreateBuildDialog } from './index'
import './index.scss'

const props = defineProps<CreateBuildDialogProps>()
const emit = defineEmits<{
  close: []
  confirm: [knowledgeBaseId: string]
}>()

const { targetKnowledgeBaseId, selectedKnowledgeBase, canConfirm, handleClose, handleConfirm }
  = useCreateBuildDialog(props, {
    close: () => emit('close'),
    confirm: knowledgeBaseId => emit('confirm', knowledgeBaseId),
  })
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="create-build-backdrop" @mousedown.self="handleClose">
      <section
        class="create-build-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-build-title"
      >
        <header class="create-build-header">
          <div class="create-build-heading">
            <span class="create-build-icon"><DatabaseZap :size="18" aria-hidden="true" /></span>
            <div>
              <h2 id="create-build-title">
                创建索引构建
              </h2>
              <p>选择需要冻结文档版本并生成向量索引的知识库。</p>
            </div>
          </div>
          <button
            class="dialog-close-button"
            type="button"
            aria-label="关闭"
            :disabled="creating"
            @click="handleClose"
          >
            <X :size="17" aria-hidden="true" />
          </button>
        </header>

        <form class="create-build-form" @submit.prevent="handleConfirm">
          <label class="create-build-field">
            <span>目标知识库</span>
            <select v-model="targetKnowledgeBaseId" :disabled="creating">
              <option
                v-for="knowledgeBase in knowledgeBases"
                :key="knowledgeBase.id"
                :value="knowledgeBase.id"
              >
                {{ knowledgeBase.name }}
              </option>
            </select>
          </label>

          <div v-if="selectedKnowledgeBase" class="create-build-summary">
            <strong>{{ selectedKnowledgeBase.name }}</strong>
            <span>当前包含 {{ selectedKnowledgeBase.document_count }} 份文档</span>
            <p>将冻结当前解析完整的文档版本，并通过已配置的嵌入模型生成索引。</p>
          </div>

          <footer class="create-build-footer">
            <button
              class="secondary-button"
              type="button"
              :disabled="creating"
              @click="handleClose"
            >
              取消
            </button>
            <button class="primary-button" type="submit" :disabled="!canConfirm">
              <DatabaseZap :size="15" aria-hidden="true" />{{ creating ? '正在创建…' : '确认创建' }}
            </button>
          </footer>
        </form>
      </section>
    </div>
  </Teleport>
</template>
