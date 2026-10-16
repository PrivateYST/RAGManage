<!-- 选文档→章节预览→选择候选→保存草稿，发布仍走既有审核。 -->
<script setup lang="ts">
import type { WikiExtractionProps } from './type'
import { AppTable } from '@/components'
import { columns, useWikiExtraction } from './index'
const props = defineProps<WikiExtractionProps>()
const emit = defineEmits<{ imported: []; busy: [value: boolean] }>()
const {
  documentId,
  ownerId,
  busy,
  importing,
  error,
  preview,
  selected,
  documents,
  candidates,
  available,
  generate,
  selectAll,
  toggle,
  save,
} = useWikiExtraction(
  props,
  () => emit('imported'),
  (value) => emit('busy', value),
)
</script>
<template>
  <div class="flex min-h-0 flex-1 flex-col gap-[16px]">
    <div
      class="grid shrink-0 gap-[12px] rounded-lg border border-border bg-secondary/30 p-[16px] sm:grid-cols-[1fr_200px_auto]"
    >
      <label class="grid gap-[6px] text-xs font-medium"
        >来源文档<select
          v-model="documentId"
          :disabled="busy || importing"
          class="rounded-md border border-input bg-background px-[10px]"
          aria-label="自动生成来源文档"
        >
          <option value="">选择已发布文档</option>
          <option v-for="document in documents" :key="document.id" :value="document.id">
            {{ document.title }}
          </option>
        </select></label
      >
      <label class="grid gap-[6px] text-xs font-medium"
        >负责人<select
          v-model="ownerId"
          :disabled="busy || importing"
          class="rounded-md border border-input bg-background px-[10px]"
          aria-label="自动生成负责人"
        >
          <option value="">待审核时指定</option>
          <option v-for="member in options.members" :key="member.id" :value="member.id">
            {{ member.display_name }}
          </option>
        </select></label
      >
      <button
        class="primary-button self-end"
        :disabled="!documentId || busy || importing"
        @click="generate"
      >
        {{ busy ? '正在生成…' : '生成预览' }}
      </button>
    </div>
    <p class="m-0 shrink-0 text-xs leading-relaxed text-muted-foreground">
      按明确标题与章节生成，内容摘自原文。选择后保存为草稿，审核发布后才参与检索。
    </p>
    <p v-if="error" class="m-0 text-xs text-destructive" role="alert">{{ error }}</p>
    <div
      v-if="busy"
      role="status"
      class="flex flex-1 items-center justify-center text-sm text-muted-foreground"
    >
      正在读取当前发布版本并整理章节…
    </div>
    <template v-else-if="preview">
      <div class="flex shrink-0 flex-wrap items-center justify-between gap-[8px] text-xs">
        <span
          >共 {{ candidates.length }} 条候选 · 可导入 {{ available.length }} 条 · 已选
          {{ selected.length }} 条</span
        >
        <div class="flex gap-[8px]">
          <button class="secondary-button" :disabled="importing" @click="selectAll">
            选择全部新词条</button
          ><button class="secondary-button" :disabled="importing" @click="selected = []">
            清空选择
          </button>
        </div>
      </div>
      <div class="min-h-0 flex-1 overflow-auto rounded-lg border border-border">
        <AppTable
          :rows="candidates"
          :columns="columns"
          row-key="key"
          client-pagination
          :page-size-options="[5, 10, 20]"
        >
          <template #cell-select="{ row }"
            ><input
              type="checkbox"
              :aria-label="`选择候选：${row.term}`"
              :checked="selected.includes(row.key)"
              :disabled="row.existing || importing"
              @change="toggle(row.key)"
          /></template>
          <template #cell-term="{ row }"
            ><strong class="text-sm">{{ row.term }}</strong>
            <p class="mt-[6px] text-xs text-muted-foreground">
              {{ row.existing ? '已有词条，跳过' : '保存后为草稿' }}
            </p>
            <p v-if="row.warning" class="text-xs text-muted-foreground">
              {{ row.warning }}
            </p></template
          >
          <template #cell-definition="{ row }"
            ><details class="text-xs">
              <summary class="cursor-pointer">查看原文摘要</summary>
              <p class="max-h-[180px] overflow-y-auto whitespace-pre-wrap leading-relaxed">
                {{ row.definition }}
              </p>
            </details></template
          >
          <template #cell-sources="{ row }"
            ><div class="grid max-h-[120px] gap-[6px] overflow-y-auto">
              <RouterLink
                v-for="source in row.sources"
                :key="source.chunk_id"
                :to="{
                  path: '/documents',
                  query: {
                    knowledge_base_id: knowledgeBaseId,
                    document_id: source.document_id,
                    version_id: source.document_version_id,
                    chunk_id: source.chunk_id,
                  },
                }"
                class="text-xs text-primary"
                >{{
                  source.locator?.page ? `第 ${source.locator.page} 页` : `片段 ${source.chunk_id}`
                }}</RouterLink
              >
            </div></template
          >
        </AppTable>
      </div>
      <div
        class="flex shrink-0 items-center justify-between gap-[12px] border-t border-border pt-[12px]"
      >
        <p class="m-0 text-xs text-muted-foreground">{{ preview.notice }}</p>
        <button
          class="primary-button shrink-0"
          :disabled="!selected.length || importing"
          @click="save"
        >
          {{ importing ? '正在保存…' : `保存 ${selected.length} 条草稿` }}
        </button>
      </div>
    </template>
    <p
      v-else-if="!error"
      class="flex flex-1 items-center justify-center text-sm text-muted-foreground"
    >
      选择文档并生成预览，已有词条会自动识别并跳过。
    </p>
  </div>
</template>
<style scoped src="./index.scss" lang="scss"></style>
