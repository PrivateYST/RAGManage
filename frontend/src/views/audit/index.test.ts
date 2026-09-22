// @vitest-environment happy-dom
/** 操作日志页面回归测试，覆盖中文映射、列表证据和不可变详情查看。 */

import type { AuditLogItem } from '@/api/audit'
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { computed, reactive, ref, shallowRef } from 'vue'
import { auditActionLabel, auditActionOptions } from './enum'
import AuditPage from './index.vue'

/** 页面渲染使用的已持久化 Release 发布审计样本。 */
const auditItem: AuditLogItem = {
  id: '18',
  tenant_id: '1',
  tenant_name: '内部工作空间',
  actor_id: '1',
  actor_name: '平台管理员',
  actor_login: 'admin',
  action: 'release.publish',
  target_type: 'knowledge_base',
  target_id: '2',
  change_summary: { release_id: 5, expected_release_id: 4 },
  request_id: '5e5f0e91-14e5-4d2b-a527-90769a2a73c9',
  created_at: '2026-09-19T12:00:00Z',
}

vi.mock('./index', () => ({
  useAuditLogs: () => ({
    auth: {
      activeSpace: { id: '1', name: '内部工作空间' },
      activeSpaceId: '1',
      user: { platform_role: 'platform_admin' },
    },
    items: ref([auditItem]),
    filters: reactive({ scope: 'space', actionPrefix: '', actor: '', targetType: '' }),
    loading: shallowRef(false),
    loadingMore: shallowRef(false),
    error: shallowRef(''),
    nextCursor: shallowRef<string | null>(null),
    selected: shallowRef<AuditLogItem | null>(null),
    isPlatformAdmin: computed(() => true),
    load: vi.fn(),
    resetFilters: vi.fn(),
  }),
}))

describe('audit page', () => {
  // 回归场景：新增用户审计动作后，筛选入口和中文名称必须同步可用。
  it('exposes user-management filters and readable user audit labels', () => {
    expect(auditActionOptions).toContainEqual({ value: 'user.', label: '用户管理' })
    expect(auditActionLabel('user.create')).toBe('创建用户')
    expect(auditActionLabel('user.update')).toBe('修改用户')
  })

  // 内容生命周期事件必须显示业务名称，便于按上传、解析和构建阶段定位问题。
  it('renders content lifecycle audit labels', () => {
    expect(auditActionLabel('document.upload')).toBe('上传文档')
    expect(auditActionLabel('document.parse.failed')).toBe('文档解析失败')
    expect(auditActionLabel('build.completed')).toBe('构建完成')
  })

  // 三类 Profile 必须各自可筛选，避免解析和嵌入配置事件混入原始编码。
  it('exposes all model and profile audit filters with readable labels', () => {
    expect(auditActionOptions).toContainEqual({
      value: 'ingestion_profile.',
      label: '解析 Profile',
    })
    expect(auditActionOptions).toContainEqual({
      value: 'embedding_profile.',
      label: '嵌入 Profile',
    })
    expect(auditActionLabel('embedding_profile.create')).toBe('创建嵌入 Profile')
    expect(auditActionLabel('runtime_profile.activate')).toBe('激活 Runtime Profile')
  })

  // 管理员诊断按实际动作前缀分别筛选，确保模型探测和检索调试均能定位。
  it('exposes diagnostic filters and readable action labels', () => {
    expect(auditActionOptions).toContainEqual({
      value: 'model_endpoint.health_check',
      label: '模型健康诊断',
    })
    expect(auditActionOptions).toContainEqual({
      value: 'search_test.',
      label: '检索诊断',
    })
    expect(auditActionLabel('model_endpoint.health_check')).toBe('检查模型端点')
    expect(auditActionLabel('search_test.run')).toBe('检索调试')
  })

  // 主路径：服务端返回的事件应展示动作、操作人、空间和关键变更摘要。
  it('renders real audit rows with human-readable labels', () => {
    const wrapper = mount(AuditPage)

    expect(wrapper.text()).toContain('发布 Release')
    expect(wrapper.text()).toContain('平台管理员')
    expect(wrapper.text()).toContain('内部工作空间')
    expect(wrapper.text()).toContain('release_id: 5')
  })

  // 详情路径：管理员能查看不可变事件编号、请求 ID 和完整摘要。
  it('opens immutable event details', async () => {
    const wrapper = mount(AuditPage)

    await wrapper.get('.table-action').trigger('click')

    const dialog = document.body.querySelector('[role="dialog"]')
    expect(dialog?.textContent).toContain('审计事件 #18')
    expect(dialog?.textContent).toContain('5e5f0e91-14e5-4d2b-a527-90769a2a73c9')
    expect(document.body.querySelector('.audit-json-block')?.textContent).toContain(
      '"release_id": 5',
    )
  })
})
