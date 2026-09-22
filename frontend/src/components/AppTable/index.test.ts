// @vitest-environment happy-dom
/**
 * AppTable 回归测试：覆盖默认字段渲染、客户端分页和服务端分页事件，
 * 防止分页组件封装后页面出现重复请求或页码越界。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import AppTable from './index.vue'

interface UserRow extends Record<string, unknown> {
  id: number
  name: string
}

const columns = [{ key: 'name', title: '名称', field: 'name' as const }]

const rows: UserRow[] = Array.from({ length: 25 }, (_, index) => ({
  id: index + 1,
  name: `用户 ${index + 1}`,
}))

describe('app table', () => {
  it('renders columns and slices client-side rows by page', async () => {
    const wrapper = mount(AppTable<UserRow>, {
      props: { rows, columns, clientPagination: true, rowKey: 'id', pageSizeOptions: [10] },
    })

    expect(wrapper.findAll('tbody tr')).toHaveLength(10)
    expect(wrapper.text()).toContain('用户 1')
    expect(wrapper.text()).not.toContain('用户 11')

    await wrapper.get('[aria-label="下一页"]').trigger('click')
    const pageRows = wrapper.findAll('tbody tr')
    expect(pageRows[0]?.text()).toBe('用户 11')
    expect(pageRows.at(-1)?.text()).toBe('用户 20')
  })

  it('emits a complete pagination state for server-side paging', async () => {
    const wrapper = mount(AppTable<UserRow>, {
      props: {
        rows: rows.slice(0, 10),
        columns,
        rowKey: 'id',
        pagination: { page: 1, pageSize: 10, total: 25 },
      },
    })

    await wrapper.get('[aria-label="下一页"]').trigger('click')
    expect(wrapper.emitted('pageChange')?.[0]).toEqual([{ page: 2, pageSize: 10, total: 25 }])
  })

  it('renders loading and empty states', () => {
    const loading = mount(AppTable<UserRow>, { props: { rows: [], columns, loading: true } })
    expect(loading.text()).toContain('正在加载')

    const empty = mount(AppTable<UserRow>, { props: { rows: [], columns, emptyText: '没有结果' } })
    expect(empty.text()).toContain('没有结果')
  })
})
