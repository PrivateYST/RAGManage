import type { NotFoundPageActions } from './type'

/** 404 页面导航逻辑：复用 Router 守卫决定登录跳转或默认工作台菜单。 */
import { useRouter } from 'vue-router'

/** 创建返回工作台动作；目标使用根路径，由认证和动态菜单守卫继续解析。 */
export function useNotFoundPage(): NotFoundPageActions {
  const router = useRouter()

  /** 返回应用入口，不硬编码某个菜单页面以兼容无权访问仪表盘的账号。 */
  function backToWorkspace(): void {
    void router.push('/')
  }

  return { backToWorkspace }
}
