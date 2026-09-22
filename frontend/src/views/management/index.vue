<!-- 平台管理工作区：负责数据表格、创建表单与用户停用确认的页面编排。 -->
<script setup lang="ts">
import type { KnowledgeBaseRow, MenuRow, TenantRow, UserRow } from '@/api/admin'
import type { AppTableColumn } from '@/components'
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  createKnowledgeBase,
  createTenant,
  createUser,
  fetchKnowledgeBases,
  fetchMenus,
  fetchTenants,
  fetchUsers,
  updateMenu,
  updateUser,
} from '@/api/admin'
import {
  AppConfirmDialog,
  AppDialog,
  AppTable,
  FileText,
  GitBranch,
  ListChecks,
  Menu as MenuIcon,
  Plus,
  Search,
  ShieldCheck,
  Users,
} from '@/components'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

const route = useRoute()
const auth = useAuthStore()
const toast = useAppToast()
const loading = ref(false)
const knowledgeBases = ref<KnowledgeBaseRow[]>([])
const menus = ref<MenuRow[]>([])
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
  { key: 'status', title: '状态' },
  { key: 'created', title: '创建时间' },
]
const menuColumns: AppTableColumn<MenuRow>[] = [
  { key: 'name', title: '菜单名称' },
  { key: 'kind', title: '类型' },
  { key: 'permission', title: '权限标识' },
  { key: 'route', title: '路由', field: 'route' },
  { key: 'visible', title: '显示' },
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
  try {
    if (route.path === '/knowledge-bases') {
      knowledgeBases.value = auth.activeSpaceId
        ? (await fetchKnowledgeBases(auth.activeSpaceId)).items
        : []
    }
    if (route.path === '/system/menus') menus.value = (await fetchMenus()).items
    if (route.path === '/system/users') users.value = (await fetchUsers()).items
    if (route.path === '/system/spaces' || route.path === '/system/users')
      tenants.value = (await fetchTenants()).items
  } catch (cause) {
    toast.error(cause instanceof Error ? cause.message : '数据加载失败')
  } finally {
    loading.value = false
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
    <div v-else-if="route.path === '/knowledge-bases'" class="content-card table-card">
      <div class="table-toolbar">
        <div class="search-box"><Search :size="16" /><input placeholder="搜索知识库" /></div>
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
        <template #cell-created="{ row }">{{
          new Date(row.created_at).toLocaleDateString('zh-CN')
        }}</template>
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
          ><button class="table-action" @click="toggleMenu(row)">
            {{ row.visible ? '隐藏' : '显示' }}
          </button></template
        >
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
          ><button class="table-action" @click="toggleUser(row)">
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
