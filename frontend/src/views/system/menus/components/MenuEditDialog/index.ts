import type { MenuForm } from '../../type'
import type { MenuEditDialogProps } from './type'
/** 菜单编辑表单逻辑：随目标菜单变化载入可编辑元数据。 */
import { ref, watch } from 'vue'

/** 清除上个菜单的值，避免切换目标时短暂显示错误对象的数据。 */
export function useMenuEditDialog(props: MenuEditDialogProps) {
  const form = ref<MenuForm>(emptyForm())

  /** 编辑器只允许名称、父级、排序与启停状态变更。 */
  function emptyForm(): MenuForm {
    return { name: '', parent_id: '', sort_order: 0, status: 'active' }
  }

  watch(
    () => props.menu,
    (menu) => {
      form.value = menu
        ? {
            name: menu.name,
            parent_id: menu.parent_id ?? '',
            sort_order: menu.sort_order,
            status: menu.status as MenuForm['status'],
          }
        : emptyForm()
    },
    { immediate: true },
  )

  return { form }
}
