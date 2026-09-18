import { apiRequest } from './client'

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
