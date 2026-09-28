// @vitest-environment happy-dom

// 回归覆盖任务中心加载失败后的可见错误和重试动作，防止 Toast 消失后页面失去恢复入口。
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, shallowRef } from 'vue'
import TasksPage from './index.vue'

const loadData = vi.fn()

vi.mock('./index', () => ({
  useTasksPage: () => ({
    knowledgeBases: shallowRef([]),
    visibleTasks: shallowRef([]),
    knowledgeBaseNames: computed(() => new Map()),
    knowledgeBaseId: shallowRef('all'),
    stateFilter: shallowRef('all'),
    loading: shallowRef(false),
    errorMessage: shallowRef('任务服务暂时不可用'),
    busyTaskId: shallowRef(null),
    stateLabel: vi.fn(),
    taskLabel: vi.fn(),
    formatDate: vi.fn(),
    progress: vi.fn(),
    loadData,
    handleRetry: vi.fn(),
    handleCancel: vi.fn(),
  }),
}))

describe('tasks page error state', () => {
  beforeEach(() => loadData.mockClear())

  it('shows the error and exposes a reload action', async () => {
    const wrapper = mount(TasksPage)
    expect(wrapper.get('[role="alert"]').text()).toContain('任务服务暂时不可用')
    await wrapper.get('.task-error button').trigger('click')
    expect(loadData).toHaveBeenCalledOnce()
  })
})
