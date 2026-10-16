/** Wiki 生命周期中文标签，列表和可访问性状态共用。 */
import type { WikiStatus } from '@/api/wiki'
export const statusLabels: Record<WikiStatus, string> = {
  draft: '草稿',
  review: '待审核',
  published: '已发布',
  retired: '已停用',
}
