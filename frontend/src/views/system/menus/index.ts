import type { CreateMenuForm, MenuForm } from './type'
/** 菜单管理逻辑：读取、创建、编辑和显隐切换，并保持路由权限反馈及时。 */
import type { MenuRow } from '@/api/admin'
import { ref } from 'vue'
import { createMenu, fetchMenus, updateMenu } from '@/api/admin'
import { useAppToast } from '@/composables/useToast'

/** 提供菜单列表状态、表单状态及服务端操作。 */
export function useMenusPage() {
  const toast = useAppToast()
  const menus = ref<MenuRow[]>([])
  const loading = ref(false)
  const loadError = ref('')
  const editingMenu = ref<MenuRow | null>(null)
  const creatingMenu = ref(false)
  const submitting = ref(false)

  /** 读取权威菜单树；失败时页面保留明确重试状态。 */
  async function loadMenus(): Promise<void> {
    loading.value = true
    loadError.value = ''
    try {
      menus.value = (await fetchMenus()).items
    } catch (cause) {
      loadError.value = cause instanceof Error ? cause.message : '菜单列表加载失败'
      toast.error(loadError.value)
    } finally {
      loading.value = false
    }
  }

  /** 初始化编辑表单；路由与权限标识保持只读，防止修改白名单契约。 */
  function openEditor(menu: MenuRow): void {
    editingMenu.value = menu
  }

  /** 新建时清除上次输入，避免意外创建重复菜单节点。 */
  function openCreator(): void {
    creatingMenu.value = true
  }

  /** 创建菜单成功后刷新列表；请求失败时保留创建表单以便修正。 */
  async function submitCreate(form: CreateMenuForm): Promise<boolean> {
    submitting.value = true
    try {
      await createMenu({
        code: form.code,
        name: form.name,
        kind: form.kind,
        ...(form.parent_id ? { parent_id: Number(form.parent_id) } : {}),
        ...(form.route ? { route: form.route } : {}),
        ...(form.icon ? { icon: form.icon } : {}),
        permission_code: form.permission_code,
        sort_order: form.sort_order,
        visible: form.visible,
      })
      toast.success('菜单已创建')
      await loadMenus()
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '菜单创建失败')
      return false
    } finally {
      submitting.value = false
    }
  }

  /** 保存可编辑元数据；父级空值明确转换为 null 表示设为顶级节点。 */
  async function submitEdit(form: MenuForm): Promise<boolean> {
    const menu = editingMenu.value
    if (!menu) return false
    submitting.value = true
    try {
      await updateMenu(menu.id, {
        name: form.name,
        parent_id: form.parent_id ? Number(form.parent_id) : null,
        sort_order: form.sort_order,
        status: form.status,
      })
      toast.success('菜单配置已更新')
      editingMenu.value = null
      await loadMenus()
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '菜单配置更新失败')
      return false
    } finally {
      submitting.value = false
    }
  }

  /** 切换可见性后重新读取菜单，确保动态路由注册与服务端状态同步。 */
  async function toggleVisibility(menu: MenuRow): Promise<void> {
    try {
      await updateMenu(menu.id, { visible: !menu.visible })
      toast.success(menu.visible ? '菜单已隐藏' : '菜单已显示')
      await loadMenus()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '菜单状态更新失败')
    }
  }

  return {
    menus,
    loading,
    loadError,
    editingMenu,
    creatingMenu,
    submitting,
    loadMenus,
    openEditor,
    openCreator,
    submitCreate,
    submitEdit,
    toggleVisibility,
  }
}
