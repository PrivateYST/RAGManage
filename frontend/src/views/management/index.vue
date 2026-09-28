<!-- 平台管理工作区：负责数据表格、创建表单与用户停用确认的页面编排。 -->
<script setup lang="ts">
import type {
  KnowledgeBaseRow,
  MenuRow,
  RoleRow,
  TenantRow,
  UserDetail,
  UserRow,
} from '@/api/admin'
import type { CreatedApiKey } from '@/api/apiKeys'
import type { AppTableColumn } from '@/components'
import type { ApiKeyCreatePayload } from '@/views/models/components/ApiKeyCreateDialog/type'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  createKnowledgeBase,
  createMenu,
  createTenant,
  createUser,
  fetchKnowledgeBases,
  fetchMenus,
  fetchRoles,
  fetchTenants,
  fetchUserDetail,
  fetchUsers,
  updateMenu,
  updateRoleMenus,
  updateUser,
} from '@/api/admin'
import { createApiKey, fetchApiKeyPlaintext } from '@/api/apiKeys'
import {
  AppConfirmDialog,
  AppDialog,
  AppTable,
  Copy,
  FileText,
  GitBranch,
  KeyRound,
  ListChecks,
  Menu as MenuIcon,
  Plus,
  Search,
  ShieldCheck,
  Users,
} from '@/components'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'
import ApiKeyCreateDialog from '@/views/models/components/ApiKeyCreateDialog/index.vue'
import ApiKeyRevealDialog from '@/views/models/components/ApiKeyRevealDialog/index.vue'

const route = useRoute()
const auth = useAuthStore()
const toast = useAppToast()
const loading = ref(false)
// 管理数据加载失败时保留页面级错误，避免只依赖短暂 Toast 导致用户误判为空数据。
const loadError = ref('')
const knowledgeBases = ref<KnowledgeBaseRow[]>([])
const menus = ref<MenuRow[]>([])
const roles = ref<RoleRow[]>([])
const users = ref<UserRow[]>([])
const tenants = ref<TenantRow[]>([])
const showUserDialog = ref(false)
const showTenantDialog = ref(false)
const showKnowledgeBaseDialog = ref(false)
const savingUser = ref(false)
const savingTenant = ref(false)
const savingKnowledgeBase = ref(false)
const pendingUserStatus = ref<UserRow | null>(null)
const updatingUserStatus = ref(false)
const editingMenu = ref<MenuRow | null>(null)
const menuForm = ref({
  name: '',
  parent_id: '',
  sort_order: 0,
  status: 'active' as 'active' | 'disabled',
})
const creatingMenu = ref(false)
const menuCreateForm = ref({
  code: '',
  name: '',
  kind: 'menu' as 'directory' | 'menu' | 'button',
  parent_id: '',
  route: '',
  icon: '',
  permission_code: '',
  sort_order: 0,
  visible: true,
})
const userDetail = ref<UserDetail | null>(null)
const userDetailOpen = ref(false)
const userDetailLoading = ref(false)
const selectedTenantForKey = ref<TenantRow | null>(null)
const tenantKeyDialogOpen = ref(false)
const tenantKeySubmitting = ref(false)
const revealedTenantKey = ref<CreatedApiKey | null>(null)
const userForm = ref({
  login: '',
  display_name: '',
  password: '',
  platform_role_code: '',
  tenant_id: '',
  tenant_role_code: 'customer_reader',
})
const tenantForm = ref({ code: '', name: '' })
const knowledgeBaseForm = ref({ tenant_id: '', name: '', description: '', purpose: 'general' })

/** 将客户 Key 的生命周期状态映射为页面文案，避免模板重复分支。 */
function tenantKeyStatusLabel(status: TenantRow['api_key_status']): string {
  if (status === 'active') return '已启用'
  if (status === 'disabled') return '已停用'
  if (status === 'expired') return '已过期'
  if (status === 'revoked') return '已撤销'
  return '未配置'
}

/** 生命周期状态使用与全局表格一致的语义色，停用和过期不能显示为成功状态。 */
function tenantKeyStatusClass(status: TenantRow['api_key_status']): string {
  return status === 'active' ? 'published' : status ? 'disabled' : ''
}

const knowledgeBaseColumns: AppTableColumn<KnowledgeBaseRow>[] = [
  { key: 'name', title: '知识库名称' },
  { key: 'purpose', title: '用途', field: 'purpose' },
  { key: 'documents', title: '文档数' },
  { key: 'status', title: '状态' },
  { key: 'updated', title: '更新时间' },
]
const tenantColumns: AppTableColumn<TenantRow>[] = [
  { key: 'name', title: '空间名称' },
  { key: 'code', title: '空间编码', field: 'code' },
  { key: 'members', title: '成员数', field: 'member_count' },
  { key: 'knowledgeBases', title: '知识库数', field: 'knowledge_base_count' },
  { key: 'apiKey', title: '客户 API Key' },
  { key: 'status', title: '状态' },
  { key: 'created', title: '创建时间' },
  { key: 'actions', title: '操作' },
]
const menuColumns: AppTableColumn<MenuRow>[] = [
  { key: 'name', title: '菜单名称' },
  { key: 'kind', title: '类型' },
  { key: 'permission', title: '权限标识' },
  { key: 'route', title: '路由', field: 'route' },
  { key: 'visible', title: '显示' },
  { key: 'actions', title: '操作' },
]
const roleColumns: AppTableColumn<RoleRow>[] = [
  { key: 'name', title: '角色' },
  { key: 'scope', title: '作用域', field: 'scope' },
  { key: 'permissions', title: '权限数' },
  { key: 'actions', title: '操作' },
]
const userColumns: AppTableColumn<UserRow>[] = [
  { key: 'user', title: '用户' },
  { key: 'role', title: '平台角色' },
  { key: 'spaces', title: '空间数', field: 'space_count' },
  { key: 'status', title: '状态' },
  { key: 'lastLogin', title: '最近登录' },
  { key: 'actions', title: '操作' },
]
const config = computed(() => ({
  '/knowledge-bases': {
    eyebrow: '知识库管理',
    title: '知识库',
    desc: '按业务用途组织文档、规则和产品资料。',
    icon: FileText,
    action: '创建知识库',
  },
  '/documents': {
    eyebrow: '知识库管理 / 医院服务规则',
    title: '文档管理',
    desc: '上传文档，查看解析状态和已发布版本。',
    icon: FileText,
    action: '上传文档',
  },
  '/releases': {
    eyebrow: '知识库管理',
    title: '发布版本',
    desc: '检查候选内容，发布或回退知识库版本。',
    icon: GitBranch,
    action: '创建构建',
  },
  '/tasks': {
    eyebrow: '后台处理',
    title: '任务中心',
    desc: '查看解析、切片和嵌入任务的执行状态。',
    icon: ListChecks,
    action: '',
  },
  '/members': {
    eyebrow: '客户空间',
    title: '空间成员',
    desc: '管理空间成员及其知识库访问授权。',
    icon: Users,
    action: '添加成员',
  },
  '/system/spaces': {
    eyebrow: '平台管理',
    title: '空间管理',
    desc: '创建客户空间并查看成员与知识库使用情况。',
    icon: Users,
    action: '新建空间',
  },
  '/system/users': {
    eyebrow: '系统管理',
    title: '用户管理',
    desc: '创建、停用和管理平台登录账号。',
    icon: Users,
    action: '新建用户',
  },
  '/system/roles': {
    eyebrow: '系统管理',
    title: '角色管理',
    desc: '配置平台、空间和知识库角色的操作范围。',
    icon: ShieldCheck,
    action: '新建角色',
  },
  '/system/menus': {
    eyebrow: '系统管理',
    title: '菜单管理',
    desc: '维护目录、页面和按钮权限标识。',
    icon: MenuIcon,
    action: '新增菜单',
  },
  '/system/audit': {
    eyebrow: '系统管理',
    title: '操作日志',
    desc: '审计登录、授权、内容和配置变更。',
    icon: FileText,
    action: '',
  },
  '/system/models': {
    eyebrow: '系统配置',
    title: '模型服务',
    desc: '登记模型端点、白名单和健康状态。',
    icon: ShieldCheck,
    action: '登记端点',
  },
  '/search-test': {
    eyebrow: '检索与评测',
    title: '检索调试',
    desc: '检查候选来源、排名和过滤原因。',
    icon: Search,
    action: '运行检索',
  },
}))
const current = computed(
  () => config.value[route.path as keyof typeof config.value] || config.value['/knowledge-bases'],
)

async function loadData(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    if (route.path === '/knowledge-bases') {
      knowledgeBases.value = auth.activeSpaceId
        ? (await fetchKnowledgeBases(auth.activeSpaceId)).items
        : []
    }
    if (route.path === '/system/menus') menus.value = (await fetchMenus()).items
    if (route.path === '/system/roles') roles.value = (await fetchRoles()).items
    if (route.path === '/system/users') users.value = (await fetchUsers()).items
    if (route.path === '/system/spaces' || route.path === '/system/users')
      tenants.value = (await fetchTenants()).items
  } catch (cause) {
    loadError.value = cause instanceof Error ? cause.message : '数据加载失败'
    toast.error(loadError.value)
  } finally {
    loading.value = false
  }
}

/** 编辑非系统角色时默认授予当前菜单集合，系统角色由迁移固定保护。 */
async function editRole(role: RoleRow): Promise<void> {
  if (role.is_system) {
    toast.error('系统角色权限由平台初始化维护，不能直接修改')
    return
  }
  try {
    await updateRoleMenus(
      role.id,
      menus.value.map((menu) => menu.id),
    )
    toast.success('角色权限已更新')
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '角色权限更新失败')
  }
}

async function toggleMenu(menu: MenuRow): Promise<void> {
  try {
    await updateMenu(menu.id, { visible: !menu.visible })
    toast.success(menu.visible ? '菜单已隐藏' : '菜单已显示')
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '菜单状态更新失败')
  }
}

/** 打开菜单元数据编辑器；权限标识和路由保持只读，避免破坏已注册的前端白名单。 */
function openMenuEditor(menu: MenuRow): void {
  editingMenu.value = menu
  menuForm.value = {
    name: menu.name,
    parent_id: menu.parent_id ?? '',
    sort_order: menu.sort_order,
    status: menu.status as 'active' | 'disabled',
  }
}

function openMenuCreator(): void {
  menuCreateForm.value = {
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
  creatingMenu.value = true
}

async function saveNewMenu(): Promise<void> {
  try {
    await createMenu({
      code: menuCreateForm.value.code,
      name: menuCreateForm.value.name,
      kind: menuCreateForm.value.kind,
      ...(menuCreateForm.value.parent_id
        ? { parent_id: Number(menuCreateForm.value.parent_id) }
        : {}),
      ...(menuCreateForm.value.route ? { route: menuCreateForm.value.route } : {}),
      ...(menuCreateForm.value.icon ? { icon: menuCreateForm.value.icon } : {}),
      permission_code: menuCreateForm.value.permission_code,
      sort_order: menuCreateForm.value.sort_order,
      visible: menuCreateForm.value.visible,
    })
    creatingMenu.value = false
    toast.success('菜单已创建')
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '菜单创建失败')
  }
}

async function saveMenu(): Promise<void> {
  if (!editingMenu.value) return
  try {
    await updateMenu(editingMenu.value.id, {
      name: menuForm.value.name,
      parent_id: menuForm.value.parent_id ? Number(menuForm.value.parent_id) : null,
      sort_order: menuForm.value.sort_order,
      status: menuForm.value.status,
    })
    toast.success('菜单配置已更新')
    editingMenu.value = null
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '菜单配置更新失败')
  }
}

function openUserDialog(): void {
  userForm.value = {
    login: '',
    display_name: '',
    password: '',
    platform_role_code: '',
    tenant_id: '',
    tenant_role_code: 'customer_reader',
  }
  showUserDialog.value = true
}

async function saveUser(): Promise<void> {
  savingUser.value = true
  try {
    await createUser({
      login: userForm.value.login,
      display_name: userForm.value.display_name,
      password: userForm.value.password,
      ...(userForm.value.platform_role_code
        ? { platform_role_code: userForm.value.platform_role_code }
        : {}),
      ...(userForm.value.tenant_id
        ? {
            tenant_id: Number(userForm.value.tenant_id),
            tenant_role_code: userForm.value.tenant_role_code,
          }
        : {}),
    })
    showUserDialog.value = false
    toast.success('用户已创建')
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '用户创建失败')
  } finally {
    savingUser.value = false
  }
}

/** 停用平台用户会立即阻止登录，先让操作者确认；恢复用户可以直接执行。 */
async function toggleUser(user: UserRow): Promise<void> {
  if (user.status === 'active') {
    pendingUserStatus.value = user
    return
  }
  await updateUserStatus(user)
}

/** 打开用户详情并读取当前空间授权与变更历史，失败时保持列表可用。 */
async function openUserDetail(user: UserRow): Promise<void> {
  userDetailOpen.value = true
  userDetailLoading.value = true
  userDetail.value = null
  try {
    userDetail.value = await fetchUserDetail(user.id)
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '用户详情加载失败')
    userDetailOpen.value = false
  } finally {
    userDetailLoading.value = false
  }
}

/** 执行已确认的平台用户状态变更并刷新列表。 */
async function updateUserStatus(user: UserRow): Promise<boolean> {
  try {
    const nextStatus = user.status === 'active' ? 'disabled' : 'active'
    await updateUser(user.id, { status: nextStatus })
    toast.success(nextStatus === 'active' ? '用户已启用' : '用户已停用')
    await loadData()
    return true
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '用户状态更新失败')
    return false
  }
}

/** 关闭用户停用确认框，不修改服务端状态。 */
function cancelUserStatus(): void {
  if (!updatingUserStatus.value) pendingUserStatus.value = null
}

/** 确认停用当前平台用户。 */
async function confirmUserStatus(): Promise<void> {
  const user = pendingUserStatus.value
  if (!user) return
  updatingUserStatus.value = true
  try {
    if (await updateUserStatus(user)) pendingUserStatus.value = null
  } finally {
    updatingUserStatus.value = false
  }
}

/** 打开客户空间的 Key 配置表单；实际创建仍由后端执行平台管理员校验。 */
function openTenantKeyDialog(tenant: TenantRow): void {
  if (tenant.status !== 'active' || tenant.api_key_id) return
  selectedTenantForKey.value = tenant
  tenantKeyDialogOpen.value = true
}

/** 为客户空间生成客户级 ``sk-`` Key，并交给一次性明文展示弹窗。 */
async function saveTenantKey(payload: ApiKeyCreatePayload): Promise<void> {
  tenantKeySubmitting.value = true
  try {
    revealedTenantKey.value = await createApiKey(payload)
    tenantKeyDialogOpen.value = false
    toast.success('客户 API Key 已配置', '请立即复制并通过安全渠道发放给客户。')
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '客户 API Key 配置失败')
  } finally {
    tenantKeySubmitting.value = false
  }
}

/** 从后端读取完整 Key 并复制；空间列表始终只展示脱敏前缀。 */
async function copyTenantKey(tenant: TenantRow): Promise<void> {
  if (!tenant.api_key_id) return
  try {
    const result = await fetchApiKeyPlaintext(tenant.api_key_id)
    await navigator.clipboard.writeText(result.raw_key)
    toast.success('完整客户 API Key 已复制', '请通过安全渠道发放，页面不会保存明文。')
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '客户 API Key 复制失败')
  }
}

/** 关闭客户 Key 的一次性明文展示，并清除页面状态。 */
function closeTenantKeyReveal(): void {
  revealedTenantKey.value = null
}

function handlePrimaryAction(): void {
  if (route.path === '/knowledge-bases') {
    knowledgeBaseForm.value = {
      tenant_id: auth.activeSpaceId,
      name: '',
      description: '',
      purpose: 'general',
    }
    showKnowledgeBaseDialog.value = true
  }
  if (route.path === '/system/users') openUserDialog()
  if (route.path === '/system/menus') openMenuCreator()
  if (route.path === '/system/spaces') {
    tenantForm.value = { code: '', name: '' }
    showTenantDialog.value = true
  }
}

async function saveKnowledgeBase(): Promise<void> {
  savingKnowledgeBase.value = true
  try {
    await createKnowledgeBase({
      ...knowledgeBaseForm.value,
      tenant_id: Number(knowledgeBaseForm.value.tenant_id),
    })
    showKnowledgeBaseDialog.value = false
    toast.success('知识库已创建')
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '知识库创建失败')
  } finally {
    savingKnowledgeBase.value = false
  }
}

async function saveTenant(): Promise<void> {
  savingTenant.value = true
  try {
    const tenant = await createTenant(tenantForm.value)
    await auth.refreshContext()
    auth.setActiveSpace(tenant.id)
    showTenantDialog.value = false
    toast.success('客户空间已创建')
    await loadData()
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '空间创建失败')
  } finally {
    savingTenant.value = false
  }
}

watch([() => route.path, () => auth.activeSpaceId], loadData, { immediate: true })
</script>

<template>
  <section class="page-section">
    <div class="page-intro">
      <div>
        <p class="eyebrow">
          {{ current.eyebrow }}
        </p>
        <h1>{{ current.title }}</h1>
        <p class="page-description">
          {{ current.desc }}
        </p>
      </div>
      <button v-if="current.action" class="primary-button" @click="handlePrimaryAction">
        <Plus :size="16" />{{ current.action }}
      </button>
    </div>
    <div v-if="loading" class="content-card module-placeholder">
      <span class="loading-spinner" />
      <p>正在加载数据…</p>
    </div>
    <div
      v-else-if="loadError"
      class="content-card flex min-h-[180px] flex-col items-center justify-center gap-[10px]"
      role="alert"
    >
      <strong class="text-sm text-destructive">管理数据加载失败</strong>
      <p class="text-xs text-muted-foreground">{{ loadError }}</p>
      <button class="secondary-button" type="button" @click="loadData">重新加载</button>
    </div>
    <div v-else-if="route.path === '/knowledge-bases'" class="content-card table-card">
      <div class="table-toolbar">
        <label class="search-box">
          <Search :size="16" aria-hidden="true" />
          <span class="sr-only">搜索知识库</span>
          <input aria-label="搜索知识库" placeholder="搜索知识库" />
        </label>
        <span class="table-count">共 {{ knowledgeBases.length }} 个知识库</span>
      </div>
      <AppTable :rows="knowledgeBases" :columns="knowledgeBaseColumns" row-key="id">
        <template #cell-name="{ row }"
          ><div class="table-name">
            <span class="kb-avatar small">库</span><strong>{{ row.name }}</strong>
          </div></template
        >
        <template #cell-documents="{ row }">{{ row.document_count }} 篇</template>
        <template #cell-status="{ row }"
          ><span class="status-pill" :class="[row.status]">{{
            row.status === 'published' ? '已发布' : row.status
          }}</span></template
        >
        <template #cell-updated="{ row }">{{
          new Date(row.updated_at).toLocaleDateString('zh-CN')
        }}</template>
      </AppTable>
    </div>
    <div v-else-if="route.path === '/system/spaces'" class="content-card table-card">
      <div class="table-toolbar">
        <span class="table-count">共 {{ tenants.length }} 个客户空间</span>
      </div>
      <AppTable :rows="tenants" :columns="tenantColumns" row-key="id">
        <template #cell-name="{ row }"
          ><strong>{{ row.name }}</strong></template
        >
        <template #cell-code="{ row }"
          ><code>{{ row.code }}</code></template
        >
        <template #cell-status="{ row }"
          ><span class="status-pill" :class="row.status === 'active' ? 'published' : 'disabled'">{{
            row.status === 'active' ? '启用' : '停用'
          }}</span></template
        >
        <template #cell-apiKey="{ row }">
          <div class="flex min-w-[170px] flex-col gap-[3px]">
            <span class="status-pill w-fit" :class="tenantKeyStatusClass(row.api_key_status)">
              {{ tenantKeyStatusLabel(row.api_key_status) }}
            </span>
            <code v-if="row.api_key_prefix">{{ row.api_key_prefix }}</code>
            <small v-if="row.api_key_id">
              已用 {{ (row.api_key_token_used ?? 0).toLocaleString() }} / 剩余
              {{ (row.api_key_token_remaining ?? 0).toLocaleString() }} Token
            </small>
          </div>
        </template>
        <template #cell-created="{ row }">{{
          new Date(row.created_at).toLocaleDateString('zh-CN')
        }}</template>
        <template #cell-actions="{ row }">
          <button
            v-if="!row.api_key_id && row.status === 'active'"
            class="table-action inline-flex items-center gap-[4px]"
            type="button"
            @click="openTenantKeyDialog(row)"
          >
            <KeyRound :size="13" />配置 Key
          </button>
          <button
            v-else-if="row.api_key_id"
            class="table-action inline-flex items-center gap-[4px]"
            type="button"
            @click="copyTenantKey(row)"
          >
            <Copy :size="13" />复制完整 Key
          </button>
          <span v-else class="text-[11px] text-muted-foreground">空间已停用</span>
        </template>
      </AppTable>
    </div>
    <div v-else-if="route.path === '/system/menus'" class="content-card table-card">
      <AppTable :rows="menus" :columns="menuColumns" row-key="id">
        <template #cell-name="{ row }"
          ><strong>{{ row.name }}</strong
          ><small>{{ row.code }}</small></template
        >
        <template #cell-kind="{ row }">{{
          row.kind === 'directory' ? '目录' : row.kind === 'menu' ? '页面' : '按钮'
        }}</template>
        <template #cell-permission="{ row }"
          ><code>{{ row.permission_code }}</code></template
        >
        <template #cell-visible="{ row }"
          ><span class="status-pill" :class="[row.visible ? 'published' : 'disabled']">{{
            row.visible ? '显示' : '隐藏'
          }}</span></template
        >
        <template #cell-actions="{ row }"
          ><button class="table-action" @click="openMenuEditor(row)">编辑</button>
          <button class="table-action" @click="toggleMenu(row)">
            {{ row.visible ? '隐藏' : '显示' }}
          </button></template
        >
      </AppTable>
    </div>
    <div v-else-if="route.path === '/system/roles'" class="content-card table-card">
      <AppTable :rows="roles" :columns="roleColumns" row-key="id">
        <template #cell-name="{ row }"
          ><strong>{{ row.name }}</strong
          ><small>{{ row.code }}</small></template
        >
        <template #cell-permissions="{ row }">{{ row.menu_ids.length }} 项</template>
        <template #cell-actions="{ row }">
          <button class="table-action" :disabled="row.is_system" @click="editRole(row)">
            {{ row.is_system ? '系统角色' : '同步当前菜单权限' }}
          </button>
        </template>
      </AppTable>
    </div>
    <div v-else-if="route.path === '/system/users'" class="content-card table-card">
      <AppTable :rows="users" :columns="userColumns" row-key="id">
        <template #cell-user="{ row }"
          ><strong>{{ row.display_name }}</strong
          ><small>{{ row.login }}</small></template
        >
        <template #cell-role="{ row }">{{ row.platform_role || '空间成员' }}</template>
        <template #cell-status="{ row }"
          ><span class="status-pill" :class="row.status === 'active' ? 'published' : 'disabled'">{{
            row.status === 'active' ? '正常' : '停用'
          }}</span></template
        >
        <template #cell-lastLogin="{ row }">{{
          row.last_login_at ? new Date(row.last_login_at).toLocaleString('zh-CN') : '尚未登录'
        }}</template>
        <template #cell-actions="{ row }"
          ><button class="table-action" @click="openUserDetail(row)">详情</button>
          <button class="table-action" @click="toggleUser(row)">
            {{ row.status === 'active' ? '停用' : '启用' }}
          </button></template
        >
      </AppTable>
    </div>
    <div v-else class="content-card module-placeholder">
      <component :is="current.icon" :size="28" />
      <h2>{{ current.title }}页面</h2>
      <p>
        页面框架和权限菜单已就绪，业务接口正在接入。当前登录用户：{{ auth.user?.display_name }}。
      </p>
      <div class="placeholder-hint">这里将展示真实数据、筛选、分页和操作反馈。</div>
    </div>
  </section>
  <AppDialog
    :open="showUserDialog"
    title="新建用户"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="showUserDialog = false"
  >
    <form class="dialog-card" @submit.prevent="saveUser">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">系统管理</p>
          <h2>新建用户</h2>
        </div>
        <button type="button" class="dialog-close" @click="showUserDialog = false">关闭</button>
      </div>
      <label
        >登录名<input v-model.trim="userForm.login" required minlength="3" maxlength="120"
      /></label>
      <label>显示名称<input v-model.trim="userForm.display_name" required maxlength="100" /></label>
      <label
        >初始密码<input v-model="userForm.password" required minlength="8" type="password"
      /></label>
      <label
        >平台角色<select v-model="userForm.platform_role_code">
          <option value="">普通用户</option>
          <option value="platform_admin">平台管理员</option>
        </select></label
      >
      <label
        >加入空间<select v-model="userForm.tenant_id">
          <option value="">暂不分配</option>
          <option v-for="tenant in tenants" :key="tenant.id" :value="tenant.id">
            {{ tenant.name }}
          </option>
        </select></label
      >
      <label v-if="userForm.tenant_id"
        >空间角色<select v-model="userForm.tenant_role_code">
          <option value="space_admin">空间管理员</option>
          <option value="customer_reader">客户用户</option>
        </select></label
      >
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="showUserDialog = false">取消</button
        ><button class="primary-button" :disabled="savingUser">
          {{ savingUser ? '保存中…' : '创建用户' }}
        </button>
      </div>
    </form>
  </AppDialog>
  <AppDialog
    :open="Boolean(editingMenu)"
    title="编辑菜单"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="editingMenu = null"
  >
    <form class="dialog-card" @submit.prevent="saveMenu">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">系统管理</p>
          <h2>编辑菜单</h2>
        </div>
        <button type="button" class="dialog-close" @click="editingMenu = null">关闭</button>
      </div>
      <label>菜单名称<input v-model.trim="menuForm.name" required maxlength="80" /></label>
      <label
        >父级菜单<select v-model="menuForm.parent_id">
          <option value="">顶级菜单</option>
          <option
            v-for="menu in menus"
            :key="menu.id"
            :value="menu.id"
            :disabled="menu.id === editingMenu?.id"
          >
            {{ menu.name }}
          </option>
        </select></label
      >
      <label
        >排序<input v-model.number="menuForm.sort_order" type="number" min="0" max="9999" required
      /></label>
      <label
        >状态<select v-model="menuForm.status">
          <option value="active">启用</option>
          <option value="disabled">停用</option>
        </select></label
      >
      <p class="text-xs text-muted-foreground">
        路由和权限标识由系统维护，编辑后会立即影响菜单展示。
      </p>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="editingMenu = null">取消</button>
        <button class="primary-button">保存菜单</button>
      </div>
    </form>
  </AppDialog>
  <AppDialog
    :open="creatingMenu"
    title="新增菜单"
    content-class="w-[min(520px,calc(100vw-2rem))]"
    @close="creatingMenu = false"
  >
    <form class="dialog-card" @submit.prevent="saveNewMenu">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">系统管理</p>
          <h2>新增菜单</h2>
        </div>
        <button type="button" class="dialog-close" @click="creatingMenu = false">关闭</button>
      </div>
      <div class="grid gap-[12px] sm:grid-cols-2">
        <label
          >编码<input v-model.trim="menuCreateForm.code" required pattern="[a-z0-9][a-z0-9_-]+"
        /></label>
        <label>名称<input v-model.trim="menuCreateForm.name" required maxlength="80" /></label>
        <label
          >类型<select v-model="menuCreateForm.kind">
            <option value="directory">目录</option>
            <option value="menu">页面</option>
            <option value="button">按钮</option>
          </select></label
        >
        <label
          >父级菜单<select v-model="menuCreateForm.parent_id">
            <option value="">顶级菜单</option>
            <option v-for="menu in menus" :key="menu.id" :value="menu.id">{{ menu.name }}</option>
          </select></label
        >
        <label
          >路由<input v-model.trim="menuCreateForm.route" placeholder="/system/example"
        /></label>
        <label>图标<input v-model.trim="menuCreateForm.icon" placeholder="Activity" /></label>
        <label
          >权限标识<input
            v-model.trim="menuCreateForm.permission_code"
            required
            placeholder="example:view"
        /></label>
        <label
          >排序<input
            v-model.number="menuCreateForm.sort_order"
            type="number"
            min="0"
            max="9999"
            required
        /></label>
      </div>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="creatingMenu = false">取消</button
        ><button class="primary-button">创建菜单</button>
      </div>
    </form>
  </AppDialog>
  <AppDialog
    :open="showTenantDialog"
    title="新建客户空间"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="showTenantDialog = false"
  >
    <form class="dialog-card" @submit.prevent="saveTenant">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">平台管理</p>
          <h2>新建客户空间</h2>
        </div>
        <button type="button" class="dialog-close" @click="showTenantDialog = false">关闭</button>
      </div>
      <label
        >空间名称<input v-model.trim="tenantForm.name" required minlength="2" maxlength="120"
      /></label>
      <label
        >空间编码<input
          v-model.trim="tenantForm.code"
          required
          minlength="2"
          maxlength="64"
          pattern="[a-z0-9][a-z0-9_-]+"
          placeholder="例如 customer-a"
      /></label>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="showTenantDialog = false">
          取消</button
        ><button class="primary-button" :disabled="savingTenant">
          {{ savingTenant ? '保存中…' : '创建空间' }}
        </button>
      </div>
    </form>
  </AppDialog>
  <AppDialog
    :open="showKnowledgeBaseDialog"
    title="创建知识库"
    content-class="w-[min(440px,calc(100vw-2rem))]"
    @close="showKnowledgeBaseDialog = false"
  >
    <form class="dialog-card" @submit.prevent="saveKnowledgeBase">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">知识库管理</p>
          <h2>创建知识库</h2>
        </div>
        <button type="button" class="dialog-close" @click="showKnowledgeBaseDialog = false">
          关闭
        </button>
      </div>
      <label>所属空间<input :value="auth.activeSpace?.name || '暂无可用空间'" disabled /></label>
      <label
        >知识库名称<input
          v-model.trim="knowledgeBaseForm.name"
          required
          minlength="2"
          maxlength="120"
      /></label>
      <label
        >业务用途<select v-model="knowledgeBaseForm.purpose">
          <option value="general">通用知识</option>
          <option value="product">产品说明</option>
          <option value="troubleshooting">故障排查</option>
          <option value="rule">业务规则</option>
        </select></label
      >
      <label
        >说明<textarea
          v-model.trim="knowledgeBaseForm.description"
          maxlength="1000"
          rows="4"
          placeholder="说明知识库覆盖的业务范围"
        />
      </label>
      <div class="dialog-actions">
        <button type="button" class="secondary-button" @click="showKnowledgeBaseDialog = false">
          取消</button
        ><button class="primary-button" :disabled="savingKnowledgeBase">
          {{ savingKnowledgeBase ? '创建中…' : '创建知识库' }}
        </button>
      </div>
    </form>
  </AppDialog>
  <ApiKeyCreateDialog
    :open="tenantKeyDialogOpen"
    :tenants="selectedTenantForKey ? [selectedTenantForKey] : []"
    :submitting="tenantKeySubmitting"
    @close="tenantKeyDialogOpen = false"
    @submit="saveTenantKey"
  />
  <ApiKeyRevealDialog
    :api-key="revealedTenantKey"
    @close="closeTenantKeyReveal"
    @copied="toast.success('客户 API Key 已复制')"
  />
  <AppDialog
    :open="userDetailOpen"
    :title="userDetail ? `${userDetail.user.display_name} · 用户详情` : '用户详情'"
    content-class="w-[min(720px,calc(100vw-2rem))]"
    @close="userDetailOpen = false"
  >
    <div v-if="userDetailLoading" class="module-placeholder min-h-[180px]" role="status">
      <span class="loading-spinner" />
      <p>正在读取授权历史…</p>
    </div>
    <div v-else-if="userDetail" class="grid gap-[20px]">
      <section>
        <p class="eyebrow">账号资料</p>
        <p class="text-sm">
          {{ userDetail.user.login }} · {{ userDetail.user.status === 'active' ? '正常' : '停用' }}
        </p>
      </section>
      <section>
        <p class="eyebrow">当前空间授权</p>
        <div v-if="userDetail.memberships.length" class="grid gap-[8px]">
          <div
            v-for="membership in userDetail.memberships"
            :key="`${membership.tenant_id}-${membership.role_code}`"
            class="rounded-md border border-border px-[12px] py-[8px] text-sm"
          >
            {{ membership.tenant_name }}（{{ membership.tenant_code }}） ·
            {{ membership.role_code }} · {{ membership.status }}
          </div>
        </div>
        <p v-else class="text-sm text-muted-foreground">暂无空间授权</p>
      </section>
      <section>
        <p class="eyebrow">授权历史</p>
        <div v-if="userDetail.history.length" class="grid gap-[8px]">
          <div
            v-for="event in userDetail.history"
            :key="event.id"
            class="rounded-md border border-border px-[12px] py-[8px] text-sm"
          >
            <strong>{{ event.action }}</strong
            ><span class="ml-[8px] text-muted-foreground">{{
              new Date(event.created_at).toLocaleString('zh-CN')
            }}</span>
          </div>
        </div>
        <p v-else class="text-sm text-muted-foreground">暂无授权变更记录</p>
      </section>
    </div>
  </AppDialog>
  <AppConfirmDialog
    :open="Boolean(pendingUserStatus)"
    :title="pendingUserStatus ? `确认停用“${pendingUserStatus.display_name}”？` : '确认停用用户'"
    description="停用后该用户将无法登录平台，已有的空间和知识库授权不会被删除。"
    confirm-label="确认停用"
    :busy="updatingUserStatus"
    @update:open="(open) => !open && cancelUserStatus()"
    @confirm="confirmUserStatus"
  />
</template>
