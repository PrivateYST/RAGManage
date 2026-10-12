<!-- 文档详情弹窗：展示版本、告警、对比和切片，并把业务动作交回页面。 -->
<script setup lang="ts">
import type { DocumentDetailDialogEmits, DocumentDetailDialogProps } from './type'
import { AppDialog, X } from '@/components'
import './index.scss'

const props = defineProps<DocumentDetailDialogProps>()
const emit = defineEmits<DocumentDetailDialogEmits>()
</script>

<template>
  <AppDialog
    :open="Boolean(props.detail || props.loading)"
    title="文档详情"
    description="查看文档版本、解析告警与切片预览。"
    content-class="w-[min(760px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <section
      class="dialog-card document-detail-dialog w-full max-w-[720px]"
      aria-labelledby="document-detail-title"
    >
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">文档详情</p>
          <h2 id="document-detail-title">
            {{ props.detail?.document.title || '正在加载…' }}
          </h2>
        </div>
        <button class="dialog-close" type="button" aria-label="关闭详情" @click="emit('close')">
          <X :size="16" />
        </button>
      </div>
      <div v-if="props.loading" class="module-placeholder detail-loading">
        <span class="loading-spinner" />
        <p>正在读取版本和切片…</p>
      </div>
      <template v-else-if="props.detail">
        <div class="mb-[12px] flex gap-[18px] text-[11px] text-muted-foreground">
          <span
            >状态：{{
              props.detail.document.status === 'active'
                ? '启用'
                : props.detail.document.status === 'disabled'
                  ? '停用'
                  : '已删除'
            }}</span
          ><span>版本数：{{ props.detail.versions.length }}</span>
        </div>
        <div
          v-if="props.detail.versions[0]?.parse_status === 'partial'"
          class="mb-[12px] rounded-md border border-status-warning/30 bg-status-warning-soft px-[10px] py-[8px] text-[10px] text-status-warning"
          role="status"
        >
          当前版本为部分完成：缺失页、表格或区域可能无法预览，以下内容仅代表已成功解析的部分。
        </div>
        <div class="flex max-h-[150px] flex-col gap-[6px] overflow-y-auto pr-[4px]">
          <div
            v-for="version in props.detail.versions"
            :key="version.id"
            class="flex items-center justify-between gap-[14px] rounded-md border border-border bg-secondary px-[10px] py-[8px]"
          >
            <div>
              <strong class="text-xs text-foreground">V{{ version.version_no }}</strong>
              <small class="mt-[2px] block text-[10px] text-muted-foreground"
                >{{ props.formatDate(version.created_at) }} ·
                {{ version.file_size.toLocaleString() }} bytes</small
              >
            </div>
            <span
              class="inline-flex min-h-[20px] items-center rounded-full px-[8px] text-[10px] font-medium"
              :class="
                version.parse_status === 'complete'
                  ? 'bg-status-up-soft text-status-up'
                  : version.parse_status === 'failed'
                    ? 'bg-destructive/10 text-destructive'
                    : 'bg-status-warning-soft text-status-warning'
              "
              >{{ props.parseStatusLabel(version.parse_status) }}</span
            >
            <button class="table-action" type="button" @click="emit('download', version.id)">
              下载
            </button>
          </div>
        </div>
        <div class="mt-[10px] flex flex-wrap justify-end gap-[8px]">
          <button class="table-action" type="button" @click="emit('reparse')">重新解析</button>
          <button class="table-action" type="button" @click="emit('rebuild')">重新嵌入</button>
        </div>
        <div class="mt-[10px] flex items-center justify-between">
          <strong class="text-xs text-foreground">版本对比</strong>
          <button
            class="table-action"
            type="button"
            :disabled="props.detail.versions.length < 2 || props.versionDiffLoading"
            @click="emit('compare')"
          >
            {{ props.versionDiffLoading ? '对比中…' : '对比最新两个版本' }}
          </button>
        </div>
        <div
          v-if="props.versionDiff"
          class="mt-[8px] rounded-md border border-border bg-secondary px-[10px] py-[8px] text-[10px]"
        >
          <div class="flex flex-wrap gap-[12px] text-muted-foreground">
            <span
              >V{{ props.versionDiff.before.version_no }} → V{{
                props.versionDiff.after.version_no
              }}</span
            >
            <span>新增 {{ props.versionDiff.diff.added_chunks }}</span>
            <span>删除 {{ props.versionDiff.diff.removed_chunks }}</span>
            <span>变更 {{ props.versionDiff.diff.changed_chunks }}</span>
          </div>
          <div v-if="props.versionDiff.diff.changes.length" class="mt-[6px] space-y-[4px]">
            <p
              v-for="(change, index) in props.versionDiff.diff.changes.slice(0, 5)"
              :key="index"
              class="m-0"
            >
              {{
                change.kind === 'added' ? '新增' : change.kind === 'removed' ? '删除' : '变更'
              }}切片：
              {{ (change.after_preview[0] || change.before_preview[0] || '').slice(0, 120) }}
            </p>
          </div>
          <p v-else class="mt-[6px] mb-0 text-muted-foreground">两个版本内容没有差异。</p>
        </div>
        <div
          v-if="props.detail.versions[0]?.warnings.length"
          class="mt-[12px] flex flex-col gap-[2px] rounded-md border border-status-warning/30 bg-status-warning-soft px-[10px] py-[8px] text-[10px] text-status-warning"
        >
          <strong class="text-[11px]">解析告警</strong>
          <span v-for="warning in props.detail.versions[0].warnings" :key="warning">{{
            warning
          }}</span>
        </div>
        <div class="mt-[15px] min-h-0">
          <div class="mb-[8px] flex items-center justify-between text-xs text-foreground">
            <strong>切片预览</strong
            ><span class="text-[10px] text-muted-foreground">{{ props.chunks.length }} 个切片</span>
          </div>
          <div
            v-if="props.chunksLoading"
            class="flex min-h-[90px] items-center justify-center gap-[8px] text-[11px] text-muted-foreground"
          >
            <span class="loading-spinner" /><span>正在读取切片…</span>
          </div>
          <div
            v-else-if="props.chunksError"
            class="min-h-[90px] rounded-md border border-status-warning/30 bg-status-warning-soft p-[12px] text-[11px] text-status-warning"
          >
            {{ props.chunksError }}
          </div>
          <div v-else-if="props.chunks.length" class="max-h-[300px] overflow-y-auto pr-[4px]">
            <article
              v-for="chunk in props.chunks"
              :key="chunk.id"
              class="rounded-md border border-border p-[10px]"
              :class="{ 'citation-target': chunk.id === props.highlightedChunkId }"
              :data-chunk-id="chunk.id"
            >
              <div class="flex items-center gap-[8px] text-[10px] text-primary">
                <span>#{{ chunk.ordinal + 1 }}</span>
                <span v-if="chunk.section_path.length">{{ chunk.section_path.join(' / ') }}</span>
                <code class="ml-auto text-[9px] text-muted-foreground">{{
                  props.formatLocator(chunk.locator)
                }}</code>
              </div>
              <p
                class="mt-[6px] whitespace-pre-wrap text-[11px] leading-[1.65] text-muted-foreground"
              >
                {{ chunk.content }}
              </p>
            </article>
          </div>
          <div v-else class="empty-state compact">
            <strong>暂无可预览切片</strong><span>解析完成后会显示原文定位。</span>
          </div>
        </div>
      </template>
    </section>
  </AppDialog>
</template>
