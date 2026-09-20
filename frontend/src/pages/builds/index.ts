import type { KnowledgeBaseRow } from '../../api/admin'
import type { BuildDetailResponse, BuildRow, ReleasePreview, ReleaseRow } from '../../api/builds'
import type { BuildMetric } from './type'
import { computed, onUnmounted, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '../../api/admin'
import {
  createBuild,
  fetchBuildDetail,
  fetchBuilds,
  fetchReleasePreview,
  fetchReleases,
  publishBuild,
  rollbackRelease,
} from '../../api/builds'
import { useAuthStore } from '../../stores/auth'
import { BUILD_STATE_LABELS } from './enum'

const POLL_INTERVAL_MS = 2500

export function useBuildsPage() {
  const auth = useAuthStore()
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const builds = ref<BuildRow[]>([])
  const releases = ref<ReleaseRow[]>([])
  const activeReleaseId = shallowRef<string | null>(null)
  const knowledgeBaseId = shallowRef('all')
  const loading = shallowRef(true)
  const creating = shallowRef(false)
  const createDialogOpen = shallowRef(false)
  const releaseDialogOpen = shallowRef(false)
  const releasePreview = shallowRef<ReleasePreview | null>(null)
  const releaseDetailOpen = shallowRef(false)
  const selectedRelease = shallowRef<ReleaseRow | null>(null)
  const releaseBuildDetail = shallowRef<BuildDetailResponse | null>(null)
  const loadingReleaseDetail = shallowRef(false)
  const releaseDetailError = shallowRef('')
  const rollbackDialogOpen = shallowRef(false)
  const rollbackTarget = shallowRef<ReleaseRow | null>(null)
  const rollingBack = shallowRef(false)
  const previewingRelease = shallowRef(false)
  const publishingRelease = shallowRef(false)
  const error = shallowRef('')
  const notice = shallowRef('')
  let pollTimer: ReturnType<typeof setInterval> | undefined

  const visibleBuilds = computed(() => builds.value)
  const selectedKnowledgeBase = computed(() =>
    knowledgeBases.value.find(item => item.id === knowledgeBaseId.value) ?? null,
  )
  const currentRelease = computed(() =>
    releases.value.find(release => release.id === activeReleaseId.value) ?? null,
  )
  const initialCreateKnowledgeBaseId = computed(() =>
    selectedKnowledgeBase.value?.id ?? knowledgeBases.value[0]?.id ?? '',
  )
  const createDisabledReason = computed(() => {
    if (loading.value)
      return '正在加载知识库'
    if (!auth.activeSpaceId)
      return '请先选择工作空间'
    if (!knowledgeBases.value.length)
      return '当前空间还没有可构建的知识库'
    return ''
  })
  const hasActiveBuild = computed(() =>
    builds.value.some(build => ['queued', 'running', 'validating'].includes(build.state)),
  )
  const metrics = computed<BuildMetric[]>(() => [
    {
      label: '构建总数',
      value: builds.value.length,
      hint: '当前空间构建记录',
      tone: 'neutral',
    },
    {
      label: '处理中',
      value: builds.value.filter(item => ['queued', 'running', 'validating'].includes(item.state)).length,
      hint: '排队、嵌入或校验',
      tone: 'running',
    },
    {
      label: '构建完成',
      value: builds.value.filter(item => item.state === 'ready').length,
      hint: '可进入发布检查',
      tone: 'ready',
    },
    {
      label: '失败',
      value: builds.value.filter(item => item.state === 'failed').length,
      hint: '可在任务中心重试',
      tone: 'failed',
    },
  ])

  function buildStateLabel(state: BuildRow['state']): string {
    return BUILD_STATE_LABELS[state]
  }

  function formatDate(value: string): string {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  }

  function progress(build: BuildRow): number {
    if (!build.chunk_count)
      return build.state === 'ready' ? 100 : 0
    return Math.min(100, Math.round(build.embedded_count / build.chunk_count * 100))
  }

  function errorCode(build: BuildRow): string {
    const code = build.error?.code
    return typeof code === 'string' ? code : '—'
  }

  function shortRevision(value: string): string {
    return value.length > 12 ? value.slice(0, 12) : value
  }

  function providerLabel(value: string): string {
    return value === 'open_webui' ? 'Open WebUI 网关' : value === 'ollama' ? 'Ollama 直连' : value
  }

  function shortEndpoint(value: string): string {
    try {
      const url = new URL(value)
      return `${url.hostname}${url.port ? `:${url.port}` : ''}`
    }
    catch {
      return value
    }
  }

  async function loadData(options: { silent?: boolean } = {}): Promise<void> {
    if (!options.silent)
      loading.value = true
    error.value = ''
    try {
      if (!auth.activeSpaceId) {
        knowledgeBases.value = []
        builds.value = []
        releases.value = []
        activeReleaseId.value = null
        return
      }
      const releaseRequest = knowledgeBaseId.value === 'all'
        ? Promise.resolve({ active_release_id: null, items: [] as ReleaseRow[] })
        : fetchReleases(knowledgeBaseId.value)
      const [knowledgeBaseResponse, buildResponse, releaseResponse] = await Promise.all([
        fetchKnowledgeBases(auth.activeSpaceId),
        fetchBuilds({
          tenantId: auth.activeSpaceId,
          ...(knowledgeBaseId.value === 'all' ? {} : { knowledgeBaseId: knowledgeBaseId.value }),
        }),
        releaseRequest,
      ])
      knowledgeBases.value = knowledgeBaseResponse.items
      builds.value = buildResponse.items
      releases.value = releaseResponse.items
      activeReleaseId.value = releaseResponse.active_release_id
      if (knowledgeBaseId.value !== 'all'
        && !knowledgeBases.value.some(item => item.id === knowledgeBaseId.value)) {
        knowledgeBaseId.value = 'all'
      }
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '构建记录加载失败'
    }
    finally {
      loading.value = false
    }
  }

  function openCreateDialog(): void {
    if (createDisabledReason.value)
      return
    createDialogOpen.value = true
  }

  function closeCreateDialog(): void {
    if (!creating.value)
      createDialogOpen.value = false
  }

  async function handleCreateBuild(targetKnowledgeBaseId: string): Promise<void> {
    const targetKnowledgeBase = knowledgeBases.value.find(
      item => item.id === targetKnowledgeBaseId,
    )
    if (!targetKnowledgeBase)
      return
    creating.value = true
    error.value = ''
    try {
      await createBuild(targetKnowledgeBase.id)
      createDialogOpen.value = false
      await loadData()
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '构建创建失败'
    }
    finally {
      creating.value = false
    }
  }

  async function openReleasePreview(build: BuildRow): Promise<void> {
    releaseDialogOpen.value = true
    previewingRelease.value = true
    releasePreview.value = null
    error.value = ''
    try {
      releasePreview.value = await fetchReleasePreview(build.id)
    }
    catch (cause) {
      releaseDialogOpen.value = false
      error.value = cause instanceof Error ? cause.message : '发布预览加载失败'
    }
    finally {
      previewingRelease.value = false
    }
  }

  function closeReleaseDialog(): void {
    if (!publishingRelease.value)
      releaseDialogOpen.value = false
  }

  async function openReleaseDetail(release: ReleaseRow): Promise<void> {
    selectedRelease.value = release
    releaseBuildDetail.value = null
    releaseDetailError.value = ''
    releaseDetailOpen.value = true
    loadingReleaseDetail.value = true
    try {
      releaseBuildDetail.value = await fetchBuildDetail(release.build_id)
    }
    catch (cause) {
      releaseDetailError.value = cause instanceof Error ? cause.message : 'Release 详情加载失败'
    }
    finally {
      loadingReleaseDetail.value = false
    }
  }

  function closeReleaseDetail(): void {
    releaseDetailOpen.value = false
  }

  function openRollbackDialog(release: ReleaseRow): void {
    if (!release.rollback_available || !currentRelease.value)
      return
    rollbackTarget.value = release
    rollbackDialogOpen.value = true
  }

  function closeRollbackDialog(): void {
    if (!rollingBack.value)
      rollbackDialogOpen.value = false
  }

  async function handleRollbackRelease(): Promise<void> {
    const target = rollbackTarget.value
    const current = currentRelease.value
    if (!target || !current || !target.rollback_available)
      return
    rollingBack.value = true
    error.value = ''
    notice.value = ''
    try {
      await rollbackRelease(target.id, current.id)
      rollbackDialogOpen.value = false
      await loadData()
      notice.value = `已回退到 Release #${target.id}，新的问答请求将使用该版本。`
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Release 回退失败'
    }
    finally {
      rollingBack.value = false
    }
  }

  async function handlePublishRelease(): Promise<void> {
    const preview = releasePreview.value
    const buildId = preview?.build.id
    if (!preview || !buildId || !preview.validation.ready)
      return
    publishingRelease.value = true
    error.value = ''
    notice.value = ''
    try {
      const result = await publishBuild(buildId, preview.expected_active_release_id)
      releaseDialogOpen.value = false
      await loadData()
      notice.value = `Release #${result.id} 发布成功，问答检索将使用该版本。`
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Release 发布失败'
    }
    finally {
      publishingRelease.value = false
    }
  }

  function startPolling(): void {
    if (pollTimer)
      clearInterval(pollTimer)
    pollTimer = setInterval(() => {
      if (hasActiveBuild.value)
        void loadData({ silent: true })
    }, POLL_INTERVAL_MS)
  }

  watch(() => auth.activeSpaceId, async () => {
    knowledgeBaseId.value = 'all'
    await loadData()
  }, { immediate: true })

  watch(knowledgeBaseId, async () => {
    await loadData()
  })

  startPolling()
  onUnmounted(() => {
    if (pollTimer)
      clearInterval(pollTimer)
  })

  return {
    knowledgeBases,
    visibleBuilds,
    releases,
    currentRelease,
    knowledgeBaseId,
    selectedKnowledgeBase,
    initialCreateKnowledgeBaseId,
    loading,
    creating,
    createDialogOpen,
    releaseDialogOpen,
    releasePreview,
    releaseDetailOpen,
    selectedRelease,
    releaseBuildDetail,
    loadingReleaseDetail,
    releaseDetailError,
    rollbackDialogOpen,
    rollbackTarget,
    rollingBack,
    previewingRelease,
    publishingRelease,
    createDisabledReason,
    error,
    notice,
    metrics,
    buildStateLabel,
    formatDate,
    progress,
    errorCode,
    shortRevision,
    providerLabel,
    shortEndpoint,
    loadData,
    openCreateDialog,
    closeCreateDialog,
    handleCreateBuild,
    openReleasePreview,
    closeReleaseDialog,
    handlePublishRelease,
    openReleaseDetail,
    closeReleaseDetail,
    openRollbackDialog,
    closeRollbackDialog,
    handleRollbackRelease,
  }
}
