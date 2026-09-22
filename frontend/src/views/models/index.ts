import type { EndpointSubmitPayload, ModelPageView } from './type'
import type { KnowledgeBaseRow } from '@/api/admin'
import type { HealthCheckResult, ModelEndpoint, ProfileCollection } from '@/api/models'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '@/api/admin'
import {
  activateRuntimeProfile,
  checkModelEndpoint,
  createEmbeddingProfile,
  createIngestionProfile,
  createModelEndpoint,
  createRuntimeProfile,
  fetchModelEndpoints,
  fetchProfiles,
  updateModelEndpoint,
} from '@/api/models'
import { useAppToast } from '@/composables/useToast'
import { useAuthStore } from '@/store/auth'

export function useModelsPage() {
  const auth = useAuthStore()
  const toast = useAppToast()
  const view = shallowRef<ModelPageView>('endpoints')
  const loading = shallowRef(false)
  const busyId = shallowRef('')
  const endpointDialogOpen = shallowRef(false)
  const gatewayKeyDialogOpen = shallowRef(false)
  const editingEndpoint = shallowRef<ModelEndpoint | null>(null)
  const pendingEndpoint = shallowRef<ModelEndpoint | null>(null)
  const endpoints = ref<ModelEndpoint[]>([])
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const selectedKnowledgeBaseId = shallowRef('')
  const profiles = ref<ProfileCollection | null>(null)
  const lastHealthResult = ref<{ endpoint: ModelEndpoint; result: HealthCheckResult } | null>(null)

  const canManageEndpoints = computed(() => auth.user?.platform_role === 'platform_admin')
  const activeEndpoints = computed(() => endpoints.value.filter((item) => item.status === 'active'))

  async function loadPage(): Promise<void> {
    loading.value = true
    try {
      const kbPromise = auth.activeSpaceId
        ? fetchKnowledgeBases(auth.activeSpaceId)
        : Promise.resolve({ items: [] as KnowledgeBaseRow[] })
      const endpointPromise = canManageEndpoints.value
        ? fetchModelEndpoints()
        : Promise.resolve({ items: [] as ModelEndpoint[] })
      const [kbResult, endpointResult] = await Promise.all([kbPromise, endpointPromise])
      knowledgeBases.value = kbResult.items
      endpoints.value = endpointResult.items
      if (!knowledgeBases.value.some((item) => item.id === selectedKnowledgeBaseId.value))
        selectedKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? ''
      if (!canManageEndpoints.value) view.value = 'profiles'
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '模型配置加载失败')
    } finally {
      loading.value = false
    }
  }

  async function loadProfiles(): Promise<void> {
    profiles.value = null
    if (!selectedKnowledgeBaseId.value) return
    try {
      profiles.value = await fetchProfiles(selectedKnowledgeBaseId.value)
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Profile 加载失败')
    }
  }

  function openCreateEndpoint(): void {
    editingEndpoint.value = null
    endpointDialogOpen.value = true
  }

  /** 打开平台级网关密钥替换弹窗。 */
  function openGatewayKeyDialog(): void {
    gatewayKeyDialogOpen.value = true
  }

  /** 保存成功后关闭弹窗并提示后续请求已切换凭据。 */
  function handleGatewayKeySaved(): void {
    gatewayKeyDialogOpen.value = false
    toast.success('模型网关 API Key 已更换', '后续模型请求将立即使用新凭据。')
  }

  function openEditEndpoint(endpoint: ModelEndpoint): void {
    editingEndpoint.value = endpoint
    endpointDialogOpen.value = true
  }

  async function submitEndpoint(payload: EndpointSubmitPayload): Promise<boolean> {
    try {
      if (payload.id) {
        await updateModelEndpoint(payload.id, {
          name: payload.name,
          base_url: payload.base_url,
          allowed_models: payload.allowed_models,
        })
        toast.success('模型端点已更新', '健康状态已重置，请重新执行检查。')
      } else {
        await createModelEndpoint(payload)
        toast.success('模型端点已登记', '请执行一次真实健康检查确认连接。')
      }
      endpointDialogOpen.value = false
      endpoints.value = (await fetchModelEndpoints()).items
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '模型端点保存失败')
      return false
    }
  }

  /** 停用会影响后续模型请求，先进入确认态；恢复启用可以直接执行。 */
  async function toggleEndpoint(endpoint: ModelEndpoint): Promise<void> {
    if (endpoint.status === 'active') {
      pendingEndpoint.value = endpoint
      return
    }
    await updateEndpointStatus(endpoint)
  }

  /** 执行已经确认的模型端点状态变更，并以服务端列表刷新页面状态。 */
  async function updateEndpointStatus(endpoint: ModelEndpoint): Promise<boolean> {
    busyId.value = `endpoint-${endpoint.id}`
    try {
      const status = endpoint.status === 'active' ? 'disabled' : 'active'
      await updateModelEndpoint(endpoint.id, { status })
      toast.success(status === 'active' ? '模型端点已启用' : '模型端点已停用')
      endpoints.value = (await fetchModelEndpoints()).items
      return true
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '端点状态更新失败')
      return false
    } finally {
      busyId.value = ''
    }
  }

  /** 关闭端点停用确认框，不产生任何服务端副作用。 */
  function cancelEndpointToggle(): void {
    if (!busyId.value) pendingEndpoint.value = null
  }

  /** 确认停用当前端点；确认状态只在请求完成后清理。 */
  async function confirmEndpointToggle(): Promise<void> {
    const endpoint = pendingEndpoint.value
    if (!endpoint) return
    if (await updateEndpointStatus(endpoint)) pendingEndpoint.value = null
  }

  async function runHealthCheck(endpoint: ModelEndpoint, modelName: string): Promise<void> {
    busyId.value = `health-${endpoint.id}`
    try {
      const result = await checkModelEndpoint(endpoint.id, modelName)
      lastHealthResult.value = { endpoint, result }
      if (result.status === 'healthy')
        toast.success('真实模型调用成功', `${result.model} · ${result.latency_ms} ms`)
      else toast.error(result.error ?? '模型检查失败')
      endpoints.value = (await fetchModelEndpoints()).items
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '模型健康检查失败')
    } finally {
      busyId.value = ''
    }
  }

  async function addIngestionProfile(input: {
    max_chars: number
    overlap_chars: number
  }): Promise<void> {
    if (!selectedKnowledgeBaseId.value) return
    try {
      await createIngestionProfile({
        knowledge_base_id: Number(selectedKnowledgeBaseId.value),
        max_chars: input.max_chars,
        overlap_chars: input.overlap_chars,
        preserve_locator: true,
      })
      toast.success('切片 Profile 已创建', '新上传或重新解析时将使用该配置。')
      await loadProfiles()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '切片 Profile 创建失败')
    }
  }

  async function addEmbeddingProfile(input: {
    endpointId: string
    modelName: string
    expectedDimension: number | null
  }): Promise<void> {
    try {
      await createEmbeddingProfile({
        model_endpoint_id: Number(input.endpointId),
        model_name: input.modelName,
        expected_dimension: input.expectedDimension,
        normalization: 'l2',
        query_instruction: '',
        document_instruction: '',
      })
      toast.success('嵌入 Profile 已创建', '真实维度检查已通过。')
      await loadProfiles()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : '嵌入 Profile 创建失败')
    }
  }

  async function addRuntimeProfile(input: {
    embeddingProfileId: string
    generationEndpointId: string
    generationModel: string
    topK: number
    contextMaxChars: number
    temperature: number
    answerRules: string
  }): Promise<void> {
    if (!selectedKnowledgeBaseId.value) return
    try {
      await createRuntimeProfile({
        knowledge_base_id: Number(selectedKnowledgeBaseId.value),
        embedding_profile_id: Number(input.embeddingProfileId),
        generation_endpoint_id: Number(input.generationEndpointId),
        generation_model: input.generationModel,
        top_k: input.topK,
        context_max_chars: input.contextMaxChars,
        temperature: input.temperature,
        answer_rules: input.answerRules,
      })
      toast.success('Runtime Profile 已创建', '激活后将进入运行链路。')
      await loadProfiles()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Runtime Profile 创建失败')
    }
  }

  async function activateRuntime(id: string): Promise<void> {
    busyId.value = `runtime-${id}`
    try {
      const result = await activateRuntimeProfile(id)
      toast.success(
        result.effect_scope === 'rebuild_required'
          ? 'Runtime Profile 已激活'
          : 'Runtime Profile 已激活并立即生效',
        result.effect_scope === 'rebuild_required'
          ? '嵌入模型发生变化，请重新构建并发布。'
          : undefined,
      )
      await loadProfiles()
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : 'Runtime Profile 激活失败')
    } finally {
      busyId.value = ''
    }
  }

  watch(() => auth.activeSpaceId, loadPage, { immediate: true })
  watch(selectedKnowledgeBaseId, loadProfiles)

  return {
    auth,
    view,
    loading,
    busyId,
    endpointDialogOpen,
    gatewayKeyDialogOpen,
    editingEndpoint,
    pendingEndpoint,
    endpoints,
    activeEndpoints,
    knowledgeBases,
    selectedKnowledgeBaseId,
    profiles,
    lastHealthResult,
    canManageEndpoints,
    loadPage,
    openCreateEndpoint,
    openGatewayKeyDialog,
    handleGatewayKeySaved,
    openEditEndpoint,
    submitEndpoint,
    toggleEndpoint,
    cancelEndpointToggle,
    confirmEndpointToggle,
    runHealthCheck,
    addIngestionProfile,
    addEmbeddingProfile,
    addRuntimeProfile,
    activateRuntime,
  }
}
