import type { BuildState } from '@/api/builds'

export const BUILD_STATE_LABELS: Record<BuildState, string> = {
  queued: '排队中',
  running: '嵌入中',
  validating: '校验中',
  ready: '构建完成',
  failed: '构建失败',
  cancelled: '已取消',
}
