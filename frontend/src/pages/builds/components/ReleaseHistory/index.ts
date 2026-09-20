import type { ReleaseHistoryProps } from './type'

export function useReleaseHistory(_props: ReleaseHistoryProps) {
  function formatDate(value: string): string {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  }

  function shortHash(value: string): string {
    return value.length > 12 ? value.slice(0, 12) : value
  }

  function providerLabel(value: string): string {
    return value === 'open_webui' ? 'Open WebUI 网关' : value === 'ollama' ? 'Ollama 直连' : value
  }

  return { formatDate, shortHash, providerLabel }
}
