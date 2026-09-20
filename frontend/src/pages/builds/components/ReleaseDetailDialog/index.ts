import type { ReleaseDetailDialogProps } from './type'
import { computed } from 'vue'

export function useReleaseDetailDialog(props: ReleaseDetailDialogProps) {
  const totalChunks = computed(() =>
    props.detail?.items.reduce((total, item) => total + item.chunk_count, 0) ?? 0,
  )
  const totalEmbeddings = computed(() =>
    props.detail?.items.reduce((total, item) => total + item.embedded_count, 0) ?? 0,
  )

  function formatDate(value: string): string {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  }

  function shortHash(value: string): string {
    return value.length > 16 ? value.slice(0, 16) : value
  }

  function providerLabel(value: string): string {
    return value === 'open_webui' ? 'Open WebUI 网关' : value === 'ollama' ? 'Ollama 直连' : value
  }

  function itemStateLabel(value: string): string {
    return value === 'completed' ? '构建完成' : value
  }

  return {
    totalChunks,
    totalEmbeddings,
    formatDate,
    shortHash,
    providerLabel,
    itemStateLabel,
  }
}
