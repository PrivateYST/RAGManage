/** 404 页面对模板暴露的导航动作契约。 */

/** 导航入口只暴露受路由守卫处理的工作台返回动作。 */
export interface NotFoundPageActions {
  backToWorkspace: () => void
}
