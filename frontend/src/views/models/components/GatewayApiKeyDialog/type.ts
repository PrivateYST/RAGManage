/** 模型网关密钥配置弹窗的输入与状态契约。 */
export interface GatewayApiKeyDialogProps {
  open: boolean
}

export interface GatewayApiKeyStatus {
  configured: boolean
  source: 'environment' | 'system'
  masked: string
}
