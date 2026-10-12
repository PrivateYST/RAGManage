/** 登录页类型：表单凭据由页面保存，认证状态仍由全局 Auth Store 管理。 */
export interface LoginFormState {
  loginName: string
  password: string
}

/** 登录提交函数通过布尔结果区分校验阻断和已完成认证尝试。 */
export type LoginSubmitResult = 'invalid' | 'authenticated' | 'rejected'
