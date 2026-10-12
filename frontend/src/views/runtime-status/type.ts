/** 运行状态页只消费健康接口返回的聚合指标，不包含租户级明细。 */
import type { RuntimeMetrics } from '@/api/health'

/** 页面读取并呈现的聚合结果类型。 */
export type RuntimeStatusMetrics = RuntimeMetrics
