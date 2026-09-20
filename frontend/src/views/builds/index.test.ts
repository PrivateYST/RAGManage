// @vitest-environment happy-dom

import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, shallowRef } from 'vue'
import BuildsPage from './index.vue'

const testState = vi.hoisted(() => ({
  openCreateDialog: vi.fn(),
  handleCreateBuild: vi.fn(),
}))

vi.mock('./index', () => ({
  useBuildsPage: () => ({
    knowledgeBases: shallowRef([
      {
        id: '1',
        tenant_id: '1',
        name: '医院服务规则',
        description: '',
        purpose: 'general',
        status: 'active',
        document_count: 1,
        updated_at: '2026-09-18T00:00:00Z',
      },
    ]),
    visibleBuilds: shallowRef([]),
    releases: shallowRef([]),
    knowledgeBaseId: shallowRef('all'),
    selectedKnowledgeBase: computed(() => null),
    loading: shallowRef(false),
    creating: shallowRef(false),
    error: shallowRef(''),
    metrics: computed(() => []),
    createDialogOpen: shallowRef(false),
    releaseDialogOpen: shallowRef(false),
    releasePreview: shallowRef(null),
    previewingRelease: shallowRef(false),
    publishingRelease: shallowRef(false),
    createDisabledReason: computed(() => ''),
    notice: shallowRef(''),
    buildStateLabel: vi.fn(),
    formatDate: vi.fn(),
    progress: vi.fn(),
    errorCode: vi.fn(),
    shortRevision: vi.fn(),
    providerLabel: vi.fn(),
    shortEndpoint: vi.fn(),
    loadData: vi.fn(),
    openCreateDialog: testState.openCreateDialog,
    closeCreateDialog: vi.fn(),
    handleCreateBuild: testState.handleCreateBuild,
    openReleasePreview: vi.fn(),
    closeReleaseDialog: vi.fn(),
    handlePublishRelease: vi.fn(),
  }),
}))

describe('builds page create action', () => {
  beforeEach(() => {
    testState.openCreateDialog.mockClear()
    testState.handleCreateBuild.mockClear()
  })

  it('opens target selection when knowledge bases exist and the list filter is all', async () => {
    const wrapper = mount(BuildsPage)
    const button = wrapper.get('.primary-button')

    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    expect(testState.openCreateDialog).toHaveBeenCalledOnce()
  })
})
