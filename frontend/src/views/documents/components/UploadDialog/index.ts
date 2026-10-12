/** 上传弹窗逻辑：本地执行文件类型/大小/空文件校验并格式化文件大小。 */
import { ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_FILE_SIZE } from './type'

/** 校验选中文件；返回错误文本或空字符串，不替代服务端内容校验。 */
export function validateUploadFile(file: File | undefined): string {
  if (!file) return ''
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!ALLOWED_UPLOAD_EXTENSIONS.includes(extension as (typeof ALLOWED_UPLOAD_EXTENSIONS)[number]))
    return '仅支持 Markdown、TXT、DOCX 和电子 PDF 文件'
  if (file.size > MAX_UPLOAD_FILE_SIZE) return '文件不能超过 50 MB'
  if (file.size === 0) return '不能上传空文件'
  return ''
}

/** 将文件字节数转成弹窗预览使用的简洁文本。 */
export function formatUploadSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}
