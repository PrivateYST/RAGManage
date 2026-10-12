/**
 * 用户角色映射回归测试：防止平台级管理员被错误绑定医院，或医院角色落成普通成员权限。
 */
import { describe, expect, it } from 'vitest'
import { toUserCreatePayload } from './index'

describe('toUserCreatePayload', () => {
  const credentials = { login: 'user1', display_name: '用户一', password: 'password123' }

  it('maps company administrators to the platform role without a hospital membership', () => {
    expect(
      toUserCreatePayload({ ...credentials, role_level: 'company_admin', tenant_id: '18' }),
    ).toEqual({ ...credentials, platform_role_code: 'platform_admin' })
  })

  it('maps hospital administrators to the hospital space administrator role', () => {
    expect(
      toUserCreatePayload({ ...credentials, role_level: 'hospital_admin', tenant_id: '18' }),
    ).toEqual({ ...credentials, tenant_id: 18, tenant_role_code: 'space_admin' })
  })

  it('maps ordinary users to the reader role in their assigned hospital', () => {
    expect(
      toUserCreatePayload({ ...credentials, role_level: 'ordinary', tenant_id: '18' }),
    ).toEqual({ ...credentials, tenant_id: 18, tenant_role_code: 'customer_reader' })
  })
})
