<!--
  创建索引构建弹框：复用 Reka Dialog 的可访问交互，业务卡片尺寸与历史版本保持一致，
  具体视觉使用 Tailwind utility，避免 Dialog 壳层与内容卡片叠加成双层弹框。
-->
<script setup lang="ts">
import type { CreateBuildDialogProps } from './type'
import { AppDialog, DatabaseZap, X } from '@/components'
import { useCreateBuildDialog } from './index'

const props = defineProps<CreateBuildDialogProps>()
const emit = defineEmits<{
  close: []
  confirm: [knowledgeBaseId: string]
}>()

const { targetKnowledgeBaseId, selectedKnowledgeBase, canConfirm, handleClose, handleConfirm } =
  useCreateBuildDialog(props, {
    close: () => emit('close'),
    confirm: (knowledgeBaseId) => emit('confirm', knowledgeBaseId),
  })
</script>

<template>
  <AppDialog
    :open="open"
    title="创建索引构建"
    content-class="w-[min(480px,calc(100vw-2rem))]"
    @close="handleClose"
  >
    <section
      class="w-full max-w-[480px] overflow-hidden rounded-lg border border-border bg-card shadow-[0_20px_50px_rgb(39_39_42_/_18%)]"
    >
      <header class="flex items-start justify-between border-b border-border p-[20px]">
        <div class="flex items-start gap-[12px]">
          <span
            class="grid size-[34px] shrink-0 place-items-center rounded-[7px] bg-[#f0ebff] text-[#6242b5]"
            ><DatabaseZap :size="18" aria-hidden="true"
          /></span>
          <div>
            <h2 id="create-build-title" class="m-0 text-base font-semibold text-foreground">
              创建索引构建
            </h2>
            <p class="mt-[6px] text-[11px] leading-[1.55] text-muted-foreground">
              选择需要冻结文档版本并生成向量索引的知识库。
            </p>
          </div>
        </div>
        <button
          class="grid size-[30px] place-items-center rounded-md border-0 bg-transparent text-muted-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50"
          type="button"
          aria-label="关闭"
          :disabled="creating"
          @click="handleClose"
        >
          <X :size="17" aria-hidden="true" />
        </button>
      </header>

      <form class="p-[20px]" @submit.prevent="handleConfirm">
        <label class="grid gap-[6px] text-xs font-semibold text-foreground">
          <span>目标知识库</span>
          <select
            v-model="targetKnowledgeBaseId"
            class="h-[36px] w-full rounded-md border border-input bg-background px-[10px] text-xs text-foreground outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="creating"
          >
            <option
              v-for="knowledgeBase in knowledgeBases"
              :key="knowledgeBase.id"
              :value="knowledgeBase.id"
            >
              {{ knowledgeBase.name }}
            </option>
          </select>
        </label>

        <div
          v-if="selectedKnowledgeBase"
          class="mt-[14px] flex flex-col gap-[4px] rounded-[7px] border border-[#e9e4f6] bg-[#faf9fd] px-[14px] py-[13px]"
        >
          <strong class="text-xs font-semibold text-foreground">{{
            selectedKnowledgeBase.name
          }}</strong>
          <span class="text-[11px] text-[#6242b5]"
            >当前包含 {{ selectedKnowledgeBase.document_count }} 份文档</span
          >
          <p class="m-0 mt-[2px] text-[11px] leading-[1.55] text-muted-foreground">
            将冻结当前解析完整的文档版本，并通过已配置的嵌入模型生成索引。
          </p>
        </div>

        <footer class="mt-[20px] flex justify-end gap-[8px]">
          <button class="secondary-button" type="button" :disabled="creating" @click="handleClose">
            取消
          </button>
          <button class="primary-button" type="submit" :disabled="!canConfirm">
            <DatabaseZap :size="15" aria-hidden="true" />{{ creating ? '正在创建…' : '确认创建' }}
          </button>
        </footer>
      </form>
    </section>
  </AppDialog>
</template>
