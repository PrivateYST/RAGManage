export interface BuildMetric {
  label: string
  value: number
  hint: string
  tone: 'neutral' | 'running' | 'ready' | 'failed'
}
