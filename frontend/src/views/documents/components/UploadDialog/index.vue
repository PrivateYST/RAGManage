<script setup lang="ts">
import type { UploadDialogProps } from './type'
import { computed, ref, useTemplateRef, watch } from 'vue'
import { AppDialog, UploadCloud } from '@/components'
import { formatUploadSize, validateUploadFile } from './index'
import './index.scss'

const props = defineProps<UploadDialogProps>()
const emit = defineEmits<{
  close: []
  upload: [file: File]
}>()

const input = useTemplateRef<HTMLInputElement>('fileInput')
const selectedFile = ref<File | null>(null)
const localError = ref('')
const fileLabel = computed(() =>
  selectedFile.value
    ? `${selectedFile.value.name}（${formatUploadSize(selectedFile.value.size)}）`
    : '选择要上传的文件',
)
const canUpload = computed(() => selectedFile.value !== null && !props.busy && !localError.value)

function validateFile(file: File | undefined): void {
  selectedFile.value = file ?? null
  localError.value = validateUploadFile(file)
}

function submit(): void {
  if (canUpload.value && selectedFile.value) emit('upload', selectedFile.value)
}

function close(): void {
  if (props.busy) return
  selectedFile.value = null
  localError.value = ''
  emit('close')
}

watch(
  () => props.open,
  (open) => {
    if (open) input.value?.focus()
  },
)
</script>

<template>
  <AppDialog
    :open="props.open"
    title="上传文档"
    content-class="w-[min(480px,calc(100vw-2rem))]"
    @close="close"
  >
    <!--
      保留历史上传弹框的领域类名：旧版通过 upload-dropzone 隐藏原生文件控件，
      并由 upload-dialog 固定 480px 宽度；外层 AppDialog 只负责遮罩、焦点和 Portal。
    -->
    <form class="dialog-card upload-dialog w-full max-w-[480px]" @submit.prevent="submit">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">知识库管理</p>
          <h2>上传文档</h2>
        </div>
        <button class="dialog-close" type="button" :disabled="props.busy" @click="close">
          关闭
        </button>
      </div>
      <p class="dialog-description -mt-[8px] mb-[16px] text-[11px] text-muted-foreground">
        上传后会创建新的文档版本，后台解析完成后才能进入构建和发布。
      </p>
      <label
        class="upload-dropzone flex min-h-[168px] cursor-pointer flex-col items-center justify-center gap-[8px] rounded-lg border border-dashed border-border bg-secondary p-[20px] text-center text-muted-foreground transition-colors hover:border-primary hover:bg-primary/5"
        :class="selectedFile ? 'border-primary bg-primary/5 text-primary' : ''"
      >
        <UploadCloud :size="25" aria-hidden="true" />
        <strong class="max-w-full truncate text-xs text-foreground">{{ fileLabel }}</strong>
        <small class="text-[10px] text-muted-foreground"
          >支持 .md、.txt、.docx、.pdf，单文件不超过 50 MB</small
        >
        <input
          ref="fileInput"
          class="sr-only"
          type="file"
          accept=".md,.txt,.docx,.pdf"
          @change="validateFile(($event.target as HTMLInputElement).files?.[0])"
        />
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
  </AppDialog>
</template>
