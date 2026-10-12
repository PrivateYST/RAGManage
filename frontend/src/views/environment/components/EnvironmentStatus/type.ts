/** 服务状态展示组件通过 Props 接收数据、通过 refresh 事件向页面请求重新检查。 */
import type { EnvironmentHealth } from '../../type'

/** 只读状态卡片的数据契约，异步行为由所属页面统一管理。 */
export interface EnvironmentStatusProps {
  health: EnvironmentHealth | null
  loading: boolean
  errorMessage: string | null
}

/** 重新检查是唯一向上事件，确保状态卡片不直接访问 API。 */
export interface EnvironmentStatusEmits {
  refresh: []
}
