export { default as AppConfirmDialog } from './AppConfirmDialog/index.vue'
export { default as AppDialog } from './AppDialog/index.vue'
export * from './AppTable'
export { default as AppTable } from './AppTable/index.vue'
export { default as AppToast } from './AppToast/index.vue'
/**
 * 全局组件公共出口：为跨页面复用的 UI 能力提供稳定导入入口。
 *
 * 业务页面不直接依赖组件文件的物理位置，后续调整组件目录时只需维护这里的导出。
 */
export * from './icons'
/** 破坏性操作专用 AlertDialog 原语，统一焦点和确认语义。 */
export * from './ui/alert-dialog'
/** shadcn-vue 风格 Dialog 原语，供业务弹窗按官网组合方式复用。 */
export * from './ui/dialog'
/** AppToast 的统一业务调用入口；反馈逻辑不应直接创建 Reka Toast。 */
export { useAppToast } from '@/composables/useToast'
