/** 存储卡片接收文件存储的聚合容量信息，容量可因后端不可用而缺失。 */
export interface FileStorageMetricsProps {
  metrics: {
    used_bytes?: number
    free_bytes?: number
    total_bytes?: number
  }
}
