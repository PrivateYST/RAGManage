<script setup lang="ts">
import type { DocumentRow } from '@/api/documents'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { FileText, MoreHorizontal } from '@/components'

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

function formatSize(size: number | null): string {
  if (!size) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN', { hour12: false }) : '—'
}
</script>

<template>
  <div class="content-card table-card document-table-card">
    <table>
      <thead>
        <tr>
          <th>文档</th>
          <th>解析状态</th>
          <th>版本</th>
          <th>大小</th>
          <th>更新时间</th>
          <th><span class="sr-only">操作</span></th>
        </tr>
      </thead>
      <tbody v-if="props.documents.length">
        <tr v-for="document in props.documents" :key="document.id">
          <td>
            <button class="document-name-button" type="button" @click="emit('preview', document)">
              <span class="document-icon"><FileText :size="15" aria-hidden="true" /></span>
              <span class="document-name-copy"
                ><strong>{{ document.title }}</strong
                ><small>{{ document.mime_type || '未知类型' }}</small></span
              >
            </button>
          </td>
          <td>
            <span class="status-pill" :class="document.parse_status || 'disabled'">
              {{ parseLabel(document.parse_status) }}
            </span>
            <span v-if="document.published" class="published-mark">已发布</span>
          </td>
          <td>V{{ document.version_no ?? '—' }}</td>
          <td>{{ formatSize(document.file_size) }}</td>
          <td>{{ formatDate(document.updated_at) }}</td>
          <td class="document-actions-cell">
            <div class="row-actions">
              <button
                class="row-actions-trigger"
                type="button"
                aria-label="打开文档操作"
                :aria-expanded="openDocumentId === document.id"
                @click.stop="toggleActionMenu($event, document)"
              >
                <MoreHorizontal :size="16" />
              </button>
            </div>
          </td>
        </tr>
      </tbody>
      <tbody v-else>
        <tr>
          <td colspan="6">
            <div class="empty-state compact document-empty">
              <div class="empty-icon">
                <FileText :size="17" aria-hidden="true" />
              </div>
              <strong>暂无符合条件的文档</strong>
              <span>上传 Markdown、TXT、DOCX 或电子 PDF 后，解析状态会显示在这里。</span>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
  <Teleport to="body">
    <div
      v-if="openDocument"
      class="row-actions-menu row-actions-menu-floating"
      :style="menuStyle"
      @click.stop
    >
      <template v-if="openDocument">
        <button type="button" @click="handleDocumentAction('preview', openDocument)">
          查看详情
        </button>
        <button
          v-if="openDocument.status === 'active'"
          type="button"
          :disabled="props.busyId === openDocument.id"
          @click="handleDocumentAction('disable', openDocument)"
        >
          {{ props.busyId === openDocument.id ? '处理中…' : '停用文档' }}
        </button>
        <button
          v-if="openDocument.status !== 'deleted'"
          class="danger-action"
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
