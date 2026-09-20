<script setup lang="ts">
import type { KnowledgeBaseRow, MenuRow, TenantRow, UserRow } from '@/api/admin'
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
  FileText,
  GitBranch,
  ListChecks,
  Menu as MenuIcon,
  Plus,
  Search,
  ShieldCheck,
  Users,
} from '@/components'
import { useAuthStore } from '@/store/auth'

const route = useRoute()
const auth = useAuthStore()
const loading = ref(false)
const error = ref('')
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
  error.value = ''
  try {
    if (route.path === '/knowledge-bases')
      knowledgeBases.value = auth.activeSpaceId
        ? (await fetchKnowledgeBases(auth.activeSpaceId)).items
        : []
    if (route.path === '/system/menus') menus.value = (await fetchMenus()).items
    if (route.path === '/system/users') users.value = (await fetchUsers()).items
    if (route.path === '/system/spaces' || route.path === '/system/users')
      tenants.value = (await fetchTenants()).items
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '数据加载失败'
  } finally {
    loading.value = false
  }
}

async function toggleMenu(menu: MenuRow): Promise<void> {
  await updateMenu(menu.id, { visible: !menu.visible })
  await loadData()
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
  error.value = ''
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
    await loadData()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '用户创建失败'
  } finally {
    savingUser.value = false
  }
}

async function toggleUser(user: UserRow): Promise<void> {
  await updateUser(user.id, { status: user.status === 'active' ? 'disabled' : 'active' })
  await loadData()
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
  error.value = ''
  try {
    await createKnowledgeBase({
      ...knowledgeBaseForm.value,
      tenant_id: Number(knowledgeBaseForm.value.tenant_id),
    })
    showKnowledgeBaseDialog.value = false
    await loadData()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '知识库创建失败'
  } finally {
    savingKnowledgeBase.value = false
  }
}

async function saveTenant(): Promise<void> {
  savingTenant.value = true
  error.value = ''
  try {
    const tenant = await createTenant(tenantForm.value)
    await auth.refreshContext()
    auth.setActiveSpace(tenant.id)
    showTenantDialog.value = false
    await loadData()
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : '空间创建失败'
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
    <div v-if="error" class="error-banner">
      {{ error }}
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
      <table>
        <thead>
          <tr>
            <th>知识库名称</th>
            <th>用途</th>
            <th>文档数</th>
            <th>状态</th>
            <th>更新时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="knowledgeBase in knowledgeBases" :key="knowledgeBase.id">
            <td>
              <div class="table-name">
                <span class="kb-avatar small">库</span><strong>{{ knowledgeBase.name }}</strong>
              </div>
            </td>
            <td>{{ knowledgeBase.purpose }}</td>
            <td>{{ knowledgeBase.document_count }} 篇</td>
            <td>
              <span class="status-pill" :class="[knowledgeBase.status]">{{
                knowledgeBase.status === 'published' ? '已发布' : knowledgeBase.status
              }}</span>
            </td>
            <td>{{ new Date(knowledgeBase.updated_at).toLocaleDateString('zh-CN') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="route.path === '/system/spaces'" class="content-card table-card">
      <div class="table-toolbar">
        <span class="table-count">共 {{ tenants.length }} 个客户空间</span>
      </div>
      <table>
        <thead>
          <tr>
            <th>空间名称</th>
            <th>空间编码</th>
            <th>成员数</th>
            <th>知识库数</th>
            <th>状态</th>
            <th>创建时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tenant in tenants" :key="tenant.id">
            <td>
              <strong>{{ tenant.name }}</strong>
            </td>
            <td>
              <code>{{ tenant.code }}</code>
            </td>
            <td>{{ tenant.member_count }}</td>
            <td>{{ tenant.knowledge_base_count }}</td>
            <td>
              <span
                class="status-pill"
                :class="tenant.status === 'active' ? 'published' : 'disabled'"
                >{{ tenant.status === 'active' ? '启用' : '停用' }}</span
              >
            </td>
            <td>{{ new Date(tenant.created_at).toLocaleDateString('zh-CN') }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="route.path === '/system/menus'" class="content-card table-card">
      <table>
        <thead>
          <tr>
            <th>菜单名称</th>
            <th>类型</th>
            <th>权限标识</th>
            <th>路由</th>
            <th>显示</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="menu in menus" :key="menu.id">
            <td>
              <strong>{{ menu.name }}</strong
              ><small>{{ menu.code }}</small>
            </td>
            <td>
              {{ menu.kind === 'directory' ? '目录' : menu.kind === 'menu' ? '页面' : '按钮' }}
            </td>
            <td>
              <code>{{ menu.permission_code }}</code>
            </td>
            <td>{{ menu.route || '—' }}</td>
            <td>
              <span class="status-pill" :class="[menu.visible ? 'published' : 'disabled']">{{
                menu.visible ? '显示' : '隐藏'
              }}</span>
            </td>
            <td>
              <button class="table-action" @click="toggleMenu(menu)">
                {{ menu.visible ? '隐藏' : '显示' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="route.path === '/system/users'" class="content-card table-card">
      <table>
        <thead>
          <tr>
            <th>用户</th>
            <th>平台角色</th>
            <th>空间数</th>
            <th>状态</th>
            <th>最近登录</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="user in users" :key="user.id">
            <td>
              <strong>{{ user.display_name }}</strong
              ><small>{{ user.login }}</small>
            </td>
            <td>{{ user.platform_role || '空间成员' }}</td>
            <td>{{ user.space_count }}</td>
            <td>
              <span
                class="status-pill"
                :class="user.status === 'active' ? 'published' : 'disabled'"
                >{{ user.status === 'active' ? '正常' : '停用' }}</span
              >
            </td>
            <td>
              {{
                user.last_login_at
                  ? new Date(user.last_login_at).toLocaleString('zh-CN')
                  : '尚未登录'
              }}
            </td>
            <td>
              <button class="table-action" @click="toggleUser(user)">
                {{ user.status === 'active' ? '停用' : '启用' }}
              </button>
            </td>
          </tr>
        </tbody>
      </table>
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
  <div v-if="showUserDialog" class="dialog-backdrop" @click.self="showUserDialog = false">
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
  </div>
  <div v-if="showTenantDialog" class="dialog-backdrop" @click.self="showTenantDialog = false">
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
  </div>
  <div
    v-if="showKnowledgeBaseDialog"
    class="dialog-backdrop"
    @click.self="showKnowledgeBaseDialog = false"
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
  </div>
</template>
