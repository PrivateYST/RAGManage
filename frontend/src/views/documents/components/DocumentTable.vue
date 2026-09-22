<!-- 文档数据表格：负责文档行展示、分页容器内的操作入口和浮动操作菜单。 -->
<script setup lang="ts">
import type { DocumentRow } from '@/api/documents'
import type { AppTableColumn } from '@/components'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { AppTable, FileText, MoreHorizontal } from '@/components'

interface Props {
  documents: DocumentRow[]
  busyId: string | null
}

const props = defineProps<Props>()
const emit = defineEmits<{
  preview: [document: DocumentRow]
  disable: [document: DocumentRow]
  remove: [document: DocumentRow]
}>()

const openDocumentId = ref<string | null>(null)
const menuStyle = ref<Record<string, string>>({})
const openDocument = computed(
  () => props.documents.find((document) => document.id === openDocumentId.value) ?? null,
)

function closeActionMenu(): void {
  openDocumentId.value = null
}

function toggleActionMenu(event: MouseEvent, document: DocumentRow): void {
  if (openDocumentId.value === document.id) {
    closeActionMenu()
    return
  }

  const trigger = event.currentTarget as HTMLElement
  const rect = trigger.getBoundingClientRect()
  const menuWidth = 126
  const menuHeight = 116
  const gap = 6
  const left = Math.max(8, Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - 8))
  const top =
    rect.bottom + gap + menuHeight <= window.innerHeight
      ? rect.bottom + gap
      : Math.max(8, rect.top - gap - menuHeight)

  menuStyle.value = {
    left: `${left}px`,
    top: `${top}px`,
  }
  openDocumentId.value = document.id
}

function handleDocumentAction(
  action: 'preview' | 'disable' | 'remove',
  document: DocumentRow,
): void {
  closeActionMenu()
  if (action === 'preview') emit('preview', document)
  else if (action === 'disable') emit('disable', document)
  else emit('remove', document)
}

function handleOutsideClick(event: MouseEvent): void {
  const target = event.target as Node
  if (!(target instanceof Element) || !target.closest('.row-actions')) closeActionMenu()
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  window.addEventListener('scroll', closeActionMenu, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
  window.removeEventListener('scroll', closeActionMenu, true)
})

const parseLabels: Record<string, string> = {
  complete: '解析完成',
  partial: '部分完成',
  processing: '解析中',
  queued: '等待处理',
  failed: '解析失败',
  unsupported: '不支持',
}

function parseLabel(status: string | null): string {
  return status ? (parseLabels[status] ?? status) : '暂无版本'
}

/** 将解析状态映射为语义色，避免状态标签在页面中各自维护一套颜色。 */
function parseStatusClass(status: string | null): string {
  if (status === 'complete') return 'bg-status-up-soft text-status-up'
  if (status === 'failed' || status === 'unsupported') return 'bg-destructive/10 text-destructive'
  if (status === 'partial') return 'bg-status-warning-soft text-status-warning'
  return 'bg-status-warning-soft text-status-warning'
}

function formatSize(size: number | null): string {
  if (!size) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}

const columns: AppTableColumn<DocumentRow>[] = [
  { key: 'document', title: '文档', cellClass: 'px-[18px] py-[14px] align-middle' },
  { key: 'parseStatus', title: '解析状态', cellClass: 'px-[18px] py-[14px] align-middle' },
  { key: 'version', title: '版本', cellClass: 'px-[18px] py-[14px] align-middle' },
  { key: 'size', title: '大小', cellClass: 'px-[18px] py-[14px] align-middle' },
  { key: 'updated', title: '更新时间', cellClass: 'px-[18px] py-[14px] align-middle' },
  {
    key: 'actions',
    title: '操作',
    cellClass: 'w-[48px] px-[18px] py-[14px] text-right align-middle',
  },
]
</script>

<template>
  <div class="content-card table-card overflow-x-auto rounded-t-none p-0">
    <AppTable
      :rows="props.documents"
      :columns="columns"
      row-key="id"
      class="w-full min-w-[680px] text-left"
    >
      <template #cell-document="{ row: document }">
        <button
          class="flex items-center gap-[8px] text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          type="button"
          @click="emit('preview', document)"
        >
          <span
            class="grid size-[29px] shrink-0 place-items-center rounded-md bg-primary/10 text-primary"
          >
            <FileText :size="15" aria-hidden="true" />
          </span>
          <span class="flex min-w-0 flex-col"
            ><strong
              class="max-w-[340px] truncate text-xs font-semibold text-foreground hover:text-primary"
              >{{ document.title }}</strong
            ><small class="mt-[2px] text-[10px] text-muted-foreground">{{
              document.mime_type || '未知类型'
            }}</small></span
          >
        </button>
      </template>
      <template #cell-parseStatus="{ row: document }">
        <span
          class="inline-flex min-h-[20px] items-center rounded-full px-[8px] text-[10px] font-medium"
          :class="parseStatusClass(document.parse_status)"
        >
          {{ parseLabel(document.parse_status) }}
        </span>
        <span
          v-if="document.published"
          class="ml-[6px] inline-flex rounded bg-status-up-soft px-[6px] py-[2px] text-[10px] text-status-up"
          >已发布</span
        >
      </template>
      <template #cell-version="{ row: document }">V{{ document.version_no ?? '—' }}</template>
      <template #cell-size="{ row: document }">{{ formatSize(document.file_size) }}</template>
      <template #cell-updated="{ row: document }">{{ formatDate(document.updated_at) }}</template>
      <template #cell-actions="{ row: document }">
        <div class="row-actions">
          <button
            class="row-actions-trigger grid size-[28px] place-items-center rounded-md border-0 bg-transparent text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            type="button"
            aria-label="打开文档操作"
            :aria-expanded="openDocumentId === document.id"
            @click.stop="toggleActionMenu($event, document)"
          >
            <MoreHorizontal :size="16" />
          </button>
        </div>
      </template>
      <template #empty>
        <div class="empty-state compact">
          <div class="empty-icon">
            <FileText :size="17" aria-hidden="true" />
          </div>
          <strong>暂无符合条件的文档</strong>
          <span>上传 Markdown、TXT、DOCX 或电子 PDF 后，解析状态会显示在这里。</span>
        </div>
      </template>
    </AppTable>
  </div>
  <Teleport to="body">
    <div
      v-if="openDocument"
      class="row-actions-menu row-actions-menu-floating fixed z-[1000] w-[126px] rounded-md border border-border bg-card p-[4px] shadow-lg"
      :style="menuStyle"
      @click.stop
    >
      <template v-if="openDocument">
        <button
          class="block w-full rounded px-[8px] py-[6px] text-left text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          type="button"
          @click="handleDocumentAction('preview', openDocument)"
        >
          查看详情
        </button>
        <button
          v-if="openDocument.status === 'active'"
          class="block w-full rounded px-[8px] py-[6px] text-left text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50"
          type="button"
          :disabled="props.busyId === openDocument.id"
          @click="handleDocumentAction('disable', openDocument)"
        >
          {{ props.busyId === openDocument.id ? '处理中…' : '停用文档' }}
        </button>
        <button
          v-if="openDocument.status !== 'deleted'"
          class="block w-full rounded px-[8px] py-[6px] text-left text-[11px] text-destructive hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:pointer-events-none disabled:opacity-50"
          type="button"
          :disabled="props.busyId === openDocument.id"
          @click="handleDocumentAction('remove', openDocument)"
        >
          删除文档
        </button>
      </template>
    </div>
  </Teleport>
</template>
