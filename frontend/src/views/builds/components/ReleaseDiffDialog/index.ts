import type { ReleaseChange } from '@/api/builds'
import type { ReleaseDiffDialogActions, ReleaseDiffDialogProps } from './type'
import { computed } from 'vue'

const CHANGE_LABELS: Record<ReleaseChange, string> = {
  added: '新增',
  updated: '更新',
  removed: '移除',
  unchanged: '未变化',
}

export function useReleaseDiffDialog(
  props: ReleaseDiffDialogProps,
  actions: ReleaseDiffDialogActions,
) {
  const canPublish = computed(() => Boolean(props.preview?.validation.ready) && !props.publishing)
  const changedItems = computed(
    () => props.preview?.diff.items.filter((item) => item.change !== 'unchanged') ?? [],
  )
  const configChanged = computed(() => {
    const current = props.preview?.current_release
    const candidate = props.preview?.build
    if (!candidate || !current) return true
    return (
      current.embedding_definition_hash !== candidate.embedding_definition_hash ||
      current.provider !== candidate.provider ||
      current.base_url !== candidate.base_url
    )
  })

  function shortHash(value: string): string {
    return value.length > 12 ? value.slice(0, 12) : value
  }

  function providerLabel(value: string): string {
    return value === 'open_webui' ? 'Open WebUI 网关' : value === 'ollama' ? 'Ollama 直连' : value
  }

  function changeLabel(value: ReleaseChange): string {
    return CHANGE_LABELS[value]
  }

  function handleClose(): void {
    if (!props.publishing) actions.close()
  }

  function handlePublish(): void {
    if (canPublish.value) actions.publish()
  }

  return {
    canPublish,
    changedItems,
    configChanged,
    shortHash,
    providerLabel,
    changeLabel,
    handleClose,
    handlePublish,
  }
}
