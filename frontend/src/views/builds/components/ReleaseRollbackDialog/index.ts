import type { ReleaseRollbackDialogActions, ReleaseRollbackDialogProps } from './type'
import { computed } from 'vue'

export function useReleaseRollbackDialog(
  props: ReleaseRollbackDialogProps,
  actions: ReleaseRollbackDialogActions,
) {
  const canConfirm = computed(
    () =>
      Boolean(props.targetRelease?.rollback_available && props.currentRelease)
      && !props.rollingBack,
  )

  function providerLabel(value: string): string {
    return value === 'open_webui' ? 'Open WebUI 网关' : value === 'ollama' ? 'Ollama 直连' : value
  }

  function handleClose(): void {
    if (!props.rollingBack)
      actions.close()
  }

  function handleConfirm(): void {
    if (canConfirm.value)
      actions.confirm()
  }

  return { canConfirm, providerLabel, handleClose, handleConfirm }
}
