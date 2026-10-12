/** 任务状态卡片接收服务端聚合计数，不读取或展示单条任务。 */
export interface TaskMetricsProps {
  metrics: Record<string, number>
}
