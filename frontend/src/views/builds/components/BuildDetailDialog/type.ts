// 构建详情弹窗的输入输出契约：只负责展示，不改变构建状态。
import type { BuildDetailResponse, BuildRow } from '@/api/builds'

export interface BuildDetailDialogProps {
  open: boolean
  loading: boolean
  error: string
  selectedBuild: BuildRow | null
  detail: BuildDetailResponse | null
}

export interface BuildDetailDialogEmits {
  (event: 'close'): void
}
