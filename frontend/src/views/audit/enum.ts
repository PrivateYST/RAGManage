/** 操作日志页面的筛选枚举与中文展示映射，不承担服务端权限判断。 */

/** 按服务端 action 前缀筛选事件，空值表示不限制操作类型。 */
export const auditActionOptions = [
  { value: '', label: '全部操作' },
  { value: 'auth.', label: '登录与会话' },
  { value: 'user.', label: '用户管理' },
  { value: 'space_member.', label: '空间成员' },
  { value: 'knowledge_base_member.', label: '知识库授权' },
  { value: 'document.', label: '文档与版本' },
  { value: 'build.', label: '索引构建' },
  { value: 'release.', label: '发布与回退' },
  { value: 'model_endpoint.', label: '模型端点' },
  { value: 'model_endpoint.health_check', label: '模型健康诊断' },
  { value: 'ingestion_profile.', label: '解析 Profile' },
  { value: 'embedding_profile.', label: '嵌入 Profile' },
  { value: 'runtime_profile.', label: '运行 Profile' },
  { value: 'search_test.', label: '检索诊断' },
] as const

/** 按审计目标类型筛选事件，值与后端 audit_logs.target_type 保持一致。 */
export const auditTargetOptions = [
  { value: '', label: '全部对象' },
  { value: 'user', label: '用户' },
  { value: 'session', label: '会话' },
  { value: 'knowledge_base', label: '知识库' },
  { value: 'document', label: '文档' },
  { value: 'task', label: '任务' },
  { value: 'build', label: '构建' },
  { value: 'release', label: 'Release' },
  { value: 'model_endpoint', label: '模型端点' },
  { value: 'ingestion_profile', label: '解析 Profile' },
  { value: 'embedding_profile', label: '嵌入 Profile' },
  { value: 'runtime_profile', label: 'Runtime Profile' },
  { value: 'retrieval_trace', label: '检索诊断' },
] as const

/** 将稳定的审计动作编码转换为面向管理员的中文名称。 */
const actionLabels: Record<string, string> = {
  'auth.login.success': '登录成功',
  'auth.login.failed': '登录失败',
  'auth.logout': '退出登录',
  'auth.password.changed': '修改密码并撤销会话',
  'user.create': '创建用户',
  'user.update': '修改用户',
  'document.upload': '上传文档',
  'document.parse.completed': '文档解析完成',
  'document.parse.failed': '文档解析失败',
  'document.disable': '停用文档',
  'document.delete': '删除文档',
  'build.create': '创建构建',
  'build.completed': '构建完成',
  'build.failed': '构建失败',
  'model_endpoint.create': '登记模型端点',
  'model_endpoint.update': '修改模型端点',
  'model_endpoint.health_check': '检查模型端点',
  'ingestion_profile.create': '创建解析 Profile',
  'embedding_profile.create': '创建嵌入 Profile',
  'release.publish': '发布 Release',
  'release.rollback': '回退 Release',
  'runtime_profile.create': '创建 Runtime Profile',
  'runtime_profile.activate': '激活 Runtime Profile',
  'search_test.run': '检索调试',
  'space_member.add': '添加空间成员',
  'space_member.update': '修改空间成员',
  'space_member.disable': '停用空间成员',
  'knowledge_base_member.add': '添加知识库授权',
  'knowledge_base_member.update': '修改知识库授权',
  'knowledge_base_member.revoke': '撤销知识库授权',
}

/** 将审计目标编码转换为中文名称。 */
const targetLabels: Record<string, string> = {
  session: '会话',
  user: '用户',
  task: '任务',
  knowledge_base: '知识库',
  document: '文档',
  build: '构建',
  release: 'Release',
  model_endpoint: '模型端点',
  ingestion_profile: '解析 Profile',
  embedding_profile: '嵌入 Profile',
  runtime_profile: 'Runtime Profile',
  retrieval_trace: '检索诊断',
}

/** 返回动作的中文名称；未知动作保留原编码，避免新事件被空白展示。 */
export function auditActionLabel(action: string): string {
  return actionLabels[action] ?? action
}

/** 返回目标类型的中文名称；未知类型保留原编码以便诊断。 */
export function auditTargetLabel(targetType: string): string {
  return targetLabels[targetType] ?? targetType
}
