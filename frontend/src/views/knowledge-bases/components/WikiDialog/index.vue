<!-- Wiki 容器仅协调词条列表、编辑表单和历史；复用已有 AppDialog/AlertDialog。 -->
<script setup lang="ts">
import type { WikiDialogProps } from './type'
import { AppConfirmDialog } from '@/components'
import WikiEntryForm from '../WikiEntryForm/index.vue'
import WikiEntryList from '../WikiEntryList/index.vue'
import WikiExtraction from '../WikiExtraction/index.vue'
import WikiGraph from '../WikiGraph/index.vue'
import { useWikiDialog } from './index'
import './index.scss'

const props = defineProps<WikiDialogProps>()
const emit = defineEmits<{ close: [] }>()
const {
  entries,
  options,
  canManage,
  loading,
  saving,
  error,
  draft,
  revisions,
  historyTerm,
  sourceQuery,
  searching,
  pendingRetire,
  editing,
  formOpen,
  startCreate,
  view,
  extractionBusy,
  load,
  reset,
  edit,
  searchSources,
  save,
  transition,
  showHistory,
} = useWikiDialog(props)
</script>

<template>
  <!-- AppDialog 壳只提供定位与遮罩，业务根节点必须提供完整卡片，避免透出底层页面。 -->
  <div
    class="flex h-[calc(100dvh-40px)] w-full min-w-0 flex-col gap-[16px] overflow-hidden rounded-xl border border-border bg-background p-[24px] shadow-lg"
  >
    <div class="flex shrink-0 items-start justify-between gap-[16px]">
      <div class="min-w-0">
        <p class="mb-[6px] text-xs font-medium text-muted-foreground">LLM Wiki · 词条管理</p>
        <h2 class="m-0 text-lg font-semibold">{{ knowledgeBaseName }}</h2>
        <p class="mt-[8px] text-sm text-muted-foreground">
          整理词条与别名，关联原文，经审核发布后辅助检索。原文仍是回答证据。
        </p>
      </div>
      <button type="button" class="secondary-button shrink-0" @click="emit('close')">关闭</button>
    </div>
    <div
      v-if="error"
      class="flex items-center justify-between gap-3 text-sm text-destructive"
      role="alert"
    >
      {{ error }}<button class="secondary-button" @click="load">重新加载</button>
    </div>
    <div v-if="loading" class="module-placeholder" role="status">正在加载词条…</div>
    <template v-else-if="!error">
      <div
        v-if="!formOpen"
        class="flex shrink-0 gap-[8px] border-b border-border pb-[12px]"
        aria-label="Wiki视图"
      >
        <button
          :class="view === 'list' ? 'primary-button' : 'secondary-button'"
          :aria-pressed="view === 'list'"
          :disabled="extractionBusy"
          @click="view = 'list'"
        >
          词条列表
        </button>
        <button
          :class="view === 'graph' ? 'primary-button' : 'secondary-button'"
          :aria-pressed="view === 'graph'"
          :disabled="extractionBusy"
          @click="view = 'graph'"
        >
          知识图谱
        </button>
        <button
          v-if="canManage"
          :class="view === 'extract' ? 'primary-button' : 'secondary-button'"
          :aria-pressed="view === 'extract'"
          :disabled="extractionBusy"
          @click="view = 'extract'"
        >
          从文档生成
        </button>
      </div>
      <WikiGraph
        v-if="view === 'graph' && !formOpen"
        :entries="entries"
        :can-manage="canManage"
        @edit="edit"
      />
      <WikiExtraction
        v-if="view === 'extract' && !formOpen && canManage"
        :knowledge-base-id="knowledgeBaseId"
        :options="options"
        @imported="load"
        @busy="extractionBusy = $event"
      />
      <template v-if="view === 'list' || formOpen">
        <div class="flex shrink-0 items-center justify-between border-t border-border pt-[16px]">
          <div>
            <h3 class="m-0 text-sm font-semibold">{{ formOpen ? '维护词条' : '知识词条' }}</h3>
            <p class="mt-[6px] text-xs text-muted-foreground">
              共 {{ entries.length }} 条 · 仅已发布且有效的词条参与检索
            </p>
          </div>
          <button v-if="canManage && !formOpen" class="primary-button" @click="startCreate">
            新建词条
          </button>
          <button v-if="formOpen" class="secondary-button" :disabled="saving" @click="reset">
            返回列表
          </button>
        </div>
        <!-- min-h-0 允许内容收缩，滚动留在弹窗内部而不是把整个白色容器撑长。 -->
        <div v-if="!formOpen" class="min-h-0 flex-1 space-y-[16px] overflow-y-auto pr-[4px]">
          <WikiEntryList
            :entries="entries"
            :can-manage="canManage"
            :busy="saving"
            @edit="edit"
            @transition="transition"
            @retire="pendingRetire = $event"
            @history="showHistory"
          />
          <section
            v-if="historyTerm"
            class="rounded-md border border-border p-[16px]"
            aria-label="词条版本历史"
          >
            <div class="flex items-center justify-between">
              <h3 class="font-semibold">{{ historyTerm }} · 版本历史</h3>
              <button class="secondary-button" @click="historyTerm = ''">收起历史</button>
            </div>
            <details
              v-for="revision in revisions"
              :key="revision.version_no"
              class="mt-[12px] border-t border-border pt-[12px] text-sm"
            >
              <summary>
                v{{ revision.version_no }} · {{ revision.action }} ·
                {{ new Date(revision.created_at).toLocaleString('zh-CN') }}
              </summary>
              <p class="mt-2 whitespace-pre-wrap">{{ revision.snapshot.definition }}</p>
              <p class="mt-1 text-muted-foreground">
                别名：{{ revision.snapshot.aliases.join('、') || '无' }} · 来源
                {{ revision.snapshot.sources.length }} 条 · 负责人
                {{ revision.snapshot.owner_user_id || '未指定' }}
              </p>
            </details>
          </section>
        </div>
        <WikiEntryForm
          v-if="canManage && formOpen"
          v-model="draft"
          v-model:source-query="sourceQuery"
          :options="options"
          :editing="editing"
          :busy="saving"
          :searching="searching"
          @search="searchSources"
          @save="save"
          @cancel="reset"
        />
        <p v-if="!canManage" class="text-sm text-muted-foreground">
          当前为只读权限，只显示已发布词条。
        </p>
      </template>
    </template>
    <AppConfirmDialog
      :open="Boolean(pendingRetire)"
      title="停用词条？"
      description="停用后，此词条立即退出检索扩展。历史内容和版本记录会保留。"
      :busy="saving"
      @cancel="pendingRetire = null"
      @confirm="pendingRetire && transition(pendingRetire, 'retired')"
    />
  </div>
</template>
