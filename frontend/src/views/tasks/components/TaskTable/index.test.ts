import type { TaskRow } from '@/api/documents'
// @vitest-environment happy-dom
/** 任务表格回归：确保仅允许的状态显示对应操作，并将目标任务上报给页面逻辑。 */
import { mount } from '@vue/test-utils'

import { describe, expect, it } from 'vitest'
import TaskTable from './index.vue'

/** 构造最小任务行，测试重试和取消状态边界。 */
function task(state: TaskRow['state'], id: string): TaskRow {
  return {
    id,
    tenant_id: 'space-1',
    knowledge_base_id: 'kb-1',
    task_type: 'document_parse',
    state,
    attempt: 1,
    error: null,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    item_count: 2,
    completed_items: 1,
  }
}

describe('task table', () => {
  it('emits retry and cancel requests only from eligible task rows', async () => {
    const failedTask = task('failed', 'task-failed')
    const queuedTask = task('queued', 'task-queued')
    const wrapper = mount(TaskTable, {
      props: {
        rows: [failedTask, queuedTask],
        knowledgeBaseNames: new Map([['kb-1', '临床知识库']]),
        busyTaskId: null,
      },
    })

    expect(wrapper.text()).toContain('临床知识库')
    expect(wrapper.text()).toContain('1 / 2')
    await wrapper.findAll('button')[0]!.trigger('click')

    expect(wrapper.emitted('retry')?.[0]).toEqual([failedTask])
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('cancel')?.[0]).toEqual([queuedTask])
  })

  it('disables the row action while that task is being changed', () => {
    const wrapper = mount(TaskTable, {
      props: {
        rows: [task('running', 'task-running')],
        knowledgeBaseNames: new Map(),
        busyTaskId: 'task-running',
      },
    })

    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
  })
})
