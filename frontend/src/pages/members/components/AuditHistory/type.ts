import type { MembershipAuditItem } from '../../../../api/members'

export interface AuditHistoryProps {
  items: MembershipAuditItem[]
  loading: boolean
}
