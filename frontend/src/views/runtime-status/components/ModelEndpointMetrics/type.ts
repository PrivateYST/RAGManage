/** 模型端点卡片只接受平台范围的可用性汇总。 */
export interface ModelEndpointMetricsProps {
  metrics: { healthy: number; unhealthy: number; unknown: number }
}
