# AppTable 表格组件规范

## 适用范围

本规范适用于 `frontend/src` 下所有页面、页面子组件和业务组件中的数据表格。

项目中的业务表格必须统一基于全局 `AppTable` 组件实现：

```text
frontend/src/components/AppTable/
```

`AppTable` 已使用 TanStack Table 和 shadcn-vue 风格的 Table 原语，并内置加载态、空态、客户端分页和服务端分页能力。业务页面不得重复实现另一套表格结构或分页结构。

## 强制要求

- 所有数据表格必须使用全局 `<AppTable />`。
- 页面不得直接编写原生 `<table>`、`<thead>`、`<tbody>`、`<tr>`、`<th>` 或 `<td>` 来实现业务表格。
- 页面不得直接组合 `Table`、`TableHeader`、`TableBody`、`TableRow`、`TableHead`、`TableCell` 来替代 `AppTable`。
- 分页必须使用 `AppTable` 提供的分页能力，不得在页面中重复实现页码、上一页、下一页或页大小选择器。
- 业务页面只负责列定义、数据请求、筛选条件和业务单元格内容。
- 跨页面需要新增表格能力时，应扩展 `AppTable` 的公共契约，不应创建私有表格组件绕过本规范。
- 使用公共组件入口导入类型或注册辅助函数时，遵循 [shared-business-component.md](shared-business-component.md) 的导出约定。

## 基础用法

```vue
<script setup lang="ts">
import type { AppTableColumn } from '@/components'

interface UserRow {
  id: number
  name: string
  email: string
  status: 'active' | 'disabled'
}

const columns: AppTableColumn<UserRow>[] = [
  { key: 'name', title: '姓名', field: 'name' },
  { key: 'email', title: '邮箱', field: 'email' },
  {
    key: 'status',
    title: '状态',
    field: 'status',
    align: 'center',
    format: (value) => (value === 'active' ? '正常' : '禁用'),
  },
]

const rows: UserRow[] = []
</script>

<template>
  <AppTable
    :rows="rows"
    :columns="columns"
    row-key="id"
  />
</template>
```

`AppTable` 已在 `src/main.ts` 中全局注册，模板中直接使用 `<AppTable />`，不需要在页面组件中再次导入组件本身。类型仍从 `@/components` 导入。

## 客户端分页

当页面已经拥有完整数据集，并且数据量适合在浏览器中分页时，使用 `client-pagination`：

```vue
<AppTable
  :rows="rows"
  :columns="columns"
  row-key="id"
  client-pagination
  :page-size-options="[10, 20, 50]"
/>
```

客户端分页由 `AppTable` 切分 `rows`。页面不需要监听分页事件，也不需要自行计算当前页数据。

## 服务端分页

当接口只返回当前页数据时，传入受控的 `pagination`，并由页面监听分页事件重新请求接口：

```vue
<script setup lang="ts">
import type { AppTablePagination } from '@/components'
import { ref } from 'vue'

const rows = ref<UserRow[]>([])
const pagination = ref<AppTablePagination>({
  page: 1,
  pageSize: 10,
  total: 0,
})

async function loadPage(next: AppTablePagination) {
  pagination.value = next
  const result = await fetchUsers({
    page: next.page,
    pageSize: next.pageSize,
  })
  rows.value = result.items
  pagination.value = {
    ...next,
    total: result.total,
  }
}

function handlePageChange(next: AppTablePagination) {
  void loadPage(next)
}
</script>

<template>
  <AppTable
    :rows="rows"
    :columns="columns"
    :pagination="pagination"
    row-key="id"
    @page-change="handlePageChange"
    @page-size-change="handlePageChange"
  />
</template>
```

服务端分页事件携带完整的 `{ page, pageSize, total }`。页面请求接口时使用 `page` 和 `pageSize`，接口返回后同步更新 `total`。

## 自定义表头和单元格

简单字段使用 `field`，需要格式化文本时使用 `format`。需要按钮、标签、图标或复杂结构时使用具名插槽：

```vue
<AppTable :rows="rows" :columns="columns" row-key="id">
  <template #header-status="{ column }">
    <span class="font-semibold">{{ column.title }}</span>
  </template>

  <template #cell-status="{ row }">
    <span
      class="rounded-md px-2 py-1 text-xs"
      :class="row.status === 'active'
        ? 'bg-green-100 text-green-700'
        : 'bg-muted text-muted-foreground'"
    >
      {{ row.status === 'active' ? '正常' : '禁用' }}
    </span>
  </template>
</AppTable>
```

操作列不绑定 `field`，通过 `cell-<key>` 插槽渲染：

```ts
const columns: AppTableColumn<UserRow>[] = [
  ...baseColumns,
  { key: 'actions', title: '操作', align: 'right' },
]
```

```vue
<AppTable :rows="rows" :columns="columns" row-key="id">
  <template #cell-actions="{ row }">
    <button type="button" @click="editUser(row)">编辑</button>
  </template>
</AppTable>
```

## 属性透传和样式

`AppTable` 根组件支持标准 HTML 属性、ARIA 属性和 `data-*` 属性透传到外层容器：

```vue
<AppTable
  id="user-table"
  class="user-table"
  data-testid="user-table"
  aria-label="用户列表"
  :rows="rows"
  :columns="columns"
/>
```

列级样式通过 `width`、`align`、`headerClass` 和 `cellClass` 配置。页面优先使用语义变量和现有样式体系，不要为单个表格创建新的颜色、间距或交互规范。

## 状态处理

- 请求进行中传入 `loading`，不要通过清空 `rows` 模拟加载态。
- 无数据时使用默认空态，特殊文案通过 `empty-text` 或 `#empty` 插槽提供。
- 复杂空态内容使用 `#empty` 插槽，不要在页面重复编写表格结构。
- 错误反馈沿用项目统一的提示机制；表格组件只负责展示加载和空数据状态。

```vue
<AppTable
  :rows="rows"
  :columns="columns"
  :loading="loading"
  empty-text="暂无匹配结果"
/>
```

## 检查清单

新增或修改表格时，提交前确认：

- 是否使用了全局 `AppTable`？
- 是否避免了原生表格标签和页面私有分页？
- 列是否使用 `AppTableColumn<T>[]` 定义？
- 是否为稳定数据提供 `row-key`？
- 服务端分页是否由页面监听事件并同步 `pagination`？
- 复杂单元格是否使用 `cell-<key>` 插槽？
- 是否覆盖了加载态、空态和错误反馈？

