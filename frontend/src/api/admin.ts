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

export interface TenantRow {
  id: string
  code: string
  name: string
  status: string
  member_count: number
  knowledge_base_count: number
  created_at: string
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

export function updateMenu(
  id: string,
  payload: Partial<Pick<MenuRow, 'name' | 'sort_order' | 'visible' | 'status'>>,
): Promise<MenuRow> {
  return apiRequest(`/api/v1/admin/menus/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}

export function fetchUsers(): Promise<{ items: UserRow[] }> {
  return apiRequest('/api/v1/admin/users')
}

export function fetchTenants(): Promise<{ items: TenantRow[] }> {
  return apiRequest('/api/v1/admin/tenants')
}

export function createTenant(payload: { code: string, name: string }): Promise<TenantRow> {
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
  payload: { status?: 'active' | 'disabled', password?: string, display_name?: string },
): Promise<UserRow> {
  return apiRequest(`/api/v1/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) })
}
