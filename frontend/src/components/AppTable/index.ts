/** AppTable 的公共类型和页面注册辅助函数。 */
import type { App } from 'vue'
import AppTable from './index.vue'

export * from './type'
export { AppTable }

/**
 * 将 AppTable 注册为全局组件。
 *
 * 入口只在应用启动时调用一次，业务页面因此不需要重复导入表格组件。
 */
export function installAppTable(app: App): void {
  app.component('AppTable', AppTable)
}
