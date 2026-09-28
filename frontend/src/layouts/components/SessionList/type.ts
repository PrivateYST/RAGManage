/** 会话列表只接收服务端快照，并将撤销意图交回弹窗容器处理。 */
import type { AuthSession } from '@/api/auth'

export interface SessionListProps {
  items: AuthSession[]
  loading: boolean
  busyId: string
}

export interface SessionListEmits {
  (event: 'revoke', session: AuthSession): void
}
