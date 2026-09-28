/** 浏览器登录身份、菜单与会话管理 API 契约。 */
import { apiRequest } from './client'

/** 登录会话的公开元信息；凭据和客户端敏感信息不会由服务端返回。 */
export interface AuthSession {
  id: string
  created_at: string
  last_seen_at: string
  expires_at: string
  is_current: boolean
}

/** 当前账号仍有效的会话集合。 */
export interface AuthSessionList {
  items: AuthSession[]
}

export interface User {
  id: string
  login: string
  display_name: string
  platform_role: string | null
}

export interface Space {
  id: string
  code: string
  name: string
  role: string
}

export interface MenuItem {
  id: string
  code: string
  name: string
  kind: 'directory' | 'menu' | 'button'
  parent_id: string | null
  route: string | null
  icon: string | null
  permission_code: string
  sort_order: number
  visible: boolean
}

export interface AuthContext {
  user: User
  spaces: Space[]
  menus: MenuItem[]
}

export function login(loginName: string, password: string): Promise<AuthContext> {
  return apiRequest<AuthContext>('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({ login: loginName, password }),
  })
}

export function currentUser(): Promise<AuthContext> {
  return apiRequest<AuthContext>('/api/v1/auth/me')
}

export function logout(): Promise<void> {
  return apiRequest<void>('/api/v1/auth/logout', { method: 'POST' })
}

export function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  return apiRequest<void>('/api/v1/auth/password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
}

/** 查询当前浏览器账号的有效会话；服务端仅返回当前用户拥有的记录。 */
export function listSessions(): Promise<AuthSessionList> {
  return apiRequest<AuthSessionList>('/api/v1/auth/sessions')
}

/** 撤销当前用户指定的有效会话；撤销当前项时服务端同步清理认证 Cookie。 */
export function revokeSession(sessionId: string): Promise<void> {
  return apiRequest<void>(`/api/v1/auth/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}
