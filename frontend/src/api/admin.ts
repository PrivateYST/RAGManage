import { apiRequest } from './client'

export interface KnowledgeBaseRow {
  id: string
  tenant_id: string
  name: string
  description: string
  purpose: string
  status: string
  active_release_id: string | null
  document_count: number
  updated_at: string
}

export interface MenuRow {
  id: string
  code: string
  name: string
  kind: string
  parent_id: string | null
  route: string | null
  icon: string | null
  permission_code: string
  sort_order: number
  visible: boolean
  status: string
}

/** 平台角色及其当前菜单权限集合。 */
export interface RoleRow {
  id: string
  code: string
  name: string
  scope: string
  description: string
  is_system: boolean
  menu_ids: string[]
}

export interface UserRow {
  id: string
  login: string
  display_name: string
  status: string
  platform_role: string | null
  space_count: number
  last_login_at: string | null
  created_at: string
}

/** 用户详情及授权变更历史；历史摘要由后端脱敏后返回。 */
export interface UserDetail {
  user: Omit<UserRow, 'space_count'>
  memberships: Array<{
    tenant_id: string
    tenant_code: string
    tenant_name: string
    role_code: string
    status: string
    created_at: string
  }>
  history: Array<{
    id: string
    action: string
    target_type: string
    target_id: string
    change_summary: Record<string, unknown>
    created_at: string
  }>
}

export interface TenantRow {
  id: string
  code: string
  name: string
  status: string
  member_count: number
  knowledge_base_count: number
  created_at: string
  /** 当前未删除客户 Key 的管理摘要；完整 Key 永远通过受保护接口读取。 */
  api_key_id: string | null
  api_key_status: 'active' | 'disabled' | 'revoked' | 'expired' | null
  api_key_prefix: string | null
  api_key_token_limit: number | null
  api_key_token_used: number | null
  api_key_token_remaining: number | null
  api_key_expires_at: string | null
}

export function fetchKnowledgeBases(tenantId?: string): Promise<{ items: KnowledgeBaseRow[] }> {
  const query = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : ''
  return apiRequest(`/api/v1/knowledge-bases${query}`)
}

export function createKnowledgeBase(payload: {
  tenant_id: number
  name: string
  description: string
  purpose: string
}): Promise<KnowledgeBaseRow> {
  return apiRequest('/api/v1/knowledge-bases', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchMenus(): Promise<{ items: MenuRow[] }> {
  return apiRequest('/api/v1/admin/menus')
}

/** 创建菜单节点；父级 ID 为空时创建顶级节点。 */
export function createMenu(payload: {
  code: string
  name: string
  kind: 'directory' | 'menu' | 'button'
  parent_id?: number
  route?: string
  icon?: string
  permission_code: string
  sort_order: number
  visible: boolean
}): Promise<MenuRow> {
  return apiRequest('/api/v1/admin/menus', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateMenu(
  id: string,
  payload: Partial<Pick<MenuRow, 'name' | 'sort_order' | 'visible' | 'status'>> & {
    parent_id?: number | null
  },
): Promise<MenuRow> {
  return apiRequest(`/api/v1/admin/menus/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

/** 获取角色权限集合。 */
export function fetchRoles(): Promise<{ items: RoleRow[] }> {
  return apiRequest('/api/v1/admin/roles')
}

/** 原子替换非系统角色的菜单权限。 */
export function updateRoleMenus(id: string, menuIds: string[]): Promise<RoleRow> {
  return apiRequest(`/api/v1/admin/roles/${id}/menus`, {
    method: 'PATCH',
    body: JSON.stringify({ menu_ids: menuIds.map(Number) }),
  })
}

export function fetchUsers(): Promise<{ items: UserRow[] }> {
  return apiRequest('/api/v1/admin/users')
}

export function fetchTenants(): Promise<{ items: TenantRow[] }> {
  return apiRequest('/api/v1/admin/tenants')
}

export function createTenant(payload: { code: string; name: string }): Promise<TenantRow> {
  return apiRequest('/api/v1/admin/tenants', { method: 'POST', body: JSON.stringify(payload) })
}

export interface UserCreatePayload {
  login: string
  display_name: string
  password: string
  platform_role_code?: string
  tenant_id?: number
  tenant_role_code?: string
}

export function createUser(payload: UserCreatePayload): Promise<UserRow> {
  return apiRequest('/api/v1/admin/users', { method: 'POST', body: JSON.stringify(payload) })
}

export function updateUser(
  id: string,
  payload: { status?: 'active' | 'disabled'; password?: string; display_name?: string },
): Promise<UserRow> {
  return apiRequest(`/api/v1/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

/** 读取平台用户详情，服务端仅允许平台管理员调用。 */
export function fetchUserDetail(id: string): Promise<UserDetail> {
  return apiRequest(`/api/v1/admin/users/${id}`)
}
