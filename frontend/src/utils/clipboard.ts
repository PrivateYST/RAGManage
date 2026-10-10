/**
 * 提供跨部署环境的文本复制能力。
 *
 * Clipboard API 只在 HTTPS 或 localhost 等安全上下文中可用；局域网通过
 * HTTP 访问时回退到临时文本框，避免业务按钮因 `navigator.clipboard` 缺失而抛错。
 */
export async function copyText(text: string): Promise<void> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text)
    return
  }

  if (typeof document === 'undefined' || !document.execCommand) {
    throw new Error('当前浏览器不支持复制，请手动选择并复制 API Key')
  }

  const textarea = document.createElement('textarea')
  textarea.value = text
  textarea.setAttribute('readonly', '')
  textarea.style.position = 'fixed'
  textarea.style.opacity = '0'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    if (!document.execCommand('copy')) {
      throw new Error('复制操作被浏览器拒绝，请手动选择并复制 API Key')
    }
  } finally {
    textarea.remove()
  }
}
