/** 上传弹窗契约：父页面负责上传请求，弹窗只校验文件并发出事件。 */
export interface UploadDialogProps {
  open: boolean
  busy: boolean
  error: string
}

/** 允许的文件类型与大小上限属于上传交互约束，服务端仍需再次校验。 */
export const ALLOWED_UPLOAD_EXTENSIONS = ['.md', '.txt', '.docx', '.pdf'] as const
export const MAX_UPLOAD_FILE_SIZE = 50 * 1024 * 1024
