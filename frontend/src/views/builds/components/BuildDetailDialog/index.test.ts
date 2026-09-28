// @vitest-environment happy-dom

// 回归覆盖构建详情的加载、错误、空清单和逐文档展示，防止诊断入口只显示汇总而丢失失败原因。
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import BuildDetailDialog from './index.vue'
vi.mock('@/components', () => {
  const icon = defineComponent({ setup: () => () => h('span') })
  const dialog = defineComponent({
    props: { open: Boolean },
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  })
  return { AppDialog: dialog, Box: icon, FileText: icon, X: icon }
})

const mountOptions = {
  attachTo: document.body,
  global: {
    // AppDialog 使用 Teleport；测试用内联壳组件保留 slot 内容，聚焦详情分支本身。
    stubs: { AppDialog: { template: '<div><slot /></div>' } },
  },
}

const build = {
  id: 'b-1',
  tenant_id: 't-1',
  knowledge_base_id: 'kb-1',
  knowledge_base_name: '制度库',
  input_epoch: 3,
  state: 'ready' as const,
  error: null,
  task_id: 'task-1',
  embedding_profile_id: 'ep-1',
  runtime_profile_id: 'rt-1',
  model_name: 'embed',
  model_revision: 'revision-123456789',
  dimension: 1024,
  embedding_definition_hash: 'hash-123456789',
  provider: 'ollama',
  base_url: 'http://ollama:11434',
  release_id: null,
  is_active_release: false,
  document_count: 1,
  completed_documents: 1,
  chunk_count: 4,
  embedded_count: 4,
  created_at: '2026-09-20T00:00:00Z',
  updated_at: '2026-09-20T01:00:00Z',
}

function detail(
  items = [
    {
      document_id: 'd-1',
      title: '制度文档',
      document_version_id: 'dv-1',
      version_no: 2,
      artifact_id: 'a-1',
      state: 'completed',
      chunk_count: 4,
      embedded_count: 4,
      error: null,
      updated_at: '2026-09-20T01:00:00Z',
    },
  ],
) {
  return { build, items }
}

describe('build detail dialog', () => {
  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('shows loading and error states', () => {
    const loading = mount(BuildDetailDialog, {
      ...mountOptions,
      props: { open: true, loading: true, error: '', selectedBuild: build, detail: null },
    })
    expect(document.body.textContent).toContain('正在读取构建清单')
    loading.unmount()
    document.body.innerHTML = ''
    const _failed = mount(BuildDetailDialog, {
      ...mountOptions,
      props: {
        open: true,
        loading: false,
        error: '服务不可用',
        selectedBuild: build,
        detail: null,
      },
    })
    expect(document.body.textContent).toContain('服务不可用')
  })

  it('renders item processing details and empty state', () => {
    const rendered = mount(BuildDetailDialog, {
      ...mountOptions,
      props: { open: true, loading: false, error: '', selectedBuild: build, detail: detail() },
    })
    expect(document.body.textContent).toContain('制度文档')
    expect(document.body.textContent).toContain('4')
    rendered.unmount()
    document.body.innerHTML = ''
    const _empty = mount(BuildDetailDialog, {
      ...mountOptions,
      props: { open: true, loading: false, error: '', selectedBuild: build, detail: detail([]) },
    })
    expect(document.body.textContent).toContain('当前构建没有文档处理记录')
  })
})
