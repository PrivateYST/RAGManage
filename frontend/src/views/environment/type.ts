/** 环境检查页面对健康接口结果的专属语义别名。 */
import type { Health } from '@/api/health'

/** 基础依赖状态快照，由健康接口整体替换，不在页面内修改。 */
export type EnvironmentHealth = Health
