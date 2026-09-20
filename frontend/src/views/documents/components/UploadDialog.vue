<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from 'vue'
import { UploadCloud } from '@/components'

interface Props {
  open: boolean
  busy: boolean
  error: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  close: []
  upload: [file: File]
}>()

const input = useTemplateRef<HTMLInputElement>('fileInput')
const selectedFile = ref<File | null>(null)
const localError = ref('')
const allowedExtensions = ['.md', '.txt', '.docx', '.pdf']

const fileLabel = computed(() =>
  selectedFile.value
    ? `${selectedFile.value.name}（${formatSize(selectedFile.value.size)}）`
    : '选择要上传的文件',
)
const canUpload = computed(() => selectedFile.value !== null && !props.busy && !localError.value)

function formatSize(size: number): string {
  if (size < 1024)
    return `${size} B`
  if (size < 1024 * 1024)
    return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function validateFile(file: File | undefined): void {
  selectedFile.value = file ?? null
  localError.value = ''
  if (!file)
    return
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowedExtensions.includes(extension))
    localError.value = '仅支持 Markdown、TXT、DOCX 和电子 PDF 文件'
  else if (file.size > 50 * 1024 * 1024)
    localError.value = '文件不能超过 50 MB'
  else if (file.size === 0)
    localError.value = '不能上传空文件'
}

function submit(): void {
  if (canUpload.value && selectedFile.value)
    emit('upload', selectedFile.value)
}

function close(): void {
  if (props.busy)
    return
  selectedFile.value = null
  localError.value = ''
  emit('close')
}

watch(
  () => props.open,
  (open) => {
    if (open)
      input.value?.focus()
  },
)
</script>

<template>
  <div v-if="props.open" class="dialog-backdrop" @click.self="close">
    <form class="dialog-card upload-dialog" @submit.prevent="submit">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">
            知识库管理
          </p>
          <h2>上传文档</h2>
        </div>
        <button class="dialog-close" type="button" :disabled="props.busy" @click="close">
          关闭
        </button>
      </div>
      <p class="dialog-description">
        上传后会创建新的文档版本，后台解析完成后才能进入构建和发布。
      </p>
      <label class="upload-dropzone" :class="{ 'has-file': selectedFile }">
        <UploadCloud :size="25" aria-hidden="true" />
        <strong>{{ fileLabel }}</strong>
        <small>支持 .md、.txt、.docx、.pdf，单文件不超过 50 MB</small>
        <input
          ref="fileInput"
          type="file"
          accept=".md,.txt,.docx,.pdf"
          @change="validateFile(($event.target as HTMLInputElement).files?.[0])"
        >
      </label>
      <p v-if="localError || props.error" class="field-error">
        {{ localError || props.error }}
      </p>
      <div class="dialog-actions">
        <button class="secondary-button" type="button" :disabled="props.busy" @click="close">
          取消
        </button>
        <button class="primary-button" type="submit" :disabled="!canUpload">
          {{ props.busy ? '上传中…' : '开始上传' }}
        </button>
      </div>
    </form>
  </div>
</template>
