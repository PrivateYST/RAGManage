import type { CreateMenuForm } from '../../type'
/** 新建菜单表单逻辑：重置节点信息并提交给父页的服务端业务操作。 */
import { ref } from 'vue'

/** 新建表单状态由弹窗拥有，防止页面列表逻辑与表单状态耦合。 */
export function useMenuCreateDialog() {
  const form = ref<CreateMenuForm>(emptyForm())

  /** 返回新节点的缺省值，根节点和页面节点是最常见的创建起点。 */
  function emptyForm(): CreateMenuForm {
    return {
      code: '',
      name: '',
      kind: 'menu',
      parent_id: '',
      route: '',
      icon: '',
      permission_code: '',
      sort_order: 0,
      visible: true,
    }
  }

  /** 打开弹窗时清理之前的输入。 */
  function reset(): void {
    form.value = emptyForm()
  }

  return { form, reset }
}
