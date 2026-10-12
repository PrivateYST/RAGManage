/** 用户管理页面及新建用户弹窗共享的角色选择契约。 */
export type UserPlatformLevel = 'company_admin' | 'hospital_admin' | 'ordinary'

/** 新建用户表单状态；后端角色字段由角色等级映射生成。 */
export interface CreateUserForm {
  login: string
  display_name: string
  password: string
  role_level: UserPlatformLevel
  tenant_id: string
}
