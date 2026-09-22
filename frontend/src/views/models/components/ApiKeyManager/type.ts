/** API Key 管理工作区可识别的短暂成功提示。 */
export type ApiKeyManagerNotice =
  | 'API Key 已创建，请立即复制并安全下发；关闭后不会再次显示明文。'
  | 'API Key 已复制'
  | '完整 API Key 已复制，请通过安全渠道下发'
  | 'API Key 已删除并立即失效'
  | 'API Key 已启用'
  | 'API Key 已停用'
  | ''
