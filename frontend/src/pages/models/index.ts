import type { KnowledgeBaseRow } from '../../api/admin'
import type { HealthCheckResult, ModelEndpoint, ProfileCollection } from '../../api/models'
import type { EndpointSubmitPayload, ModelPageView } from './type'
import { computed, ref, shallowRef, watch } from 'vue'
import { fetchKnowledgeBases } from '../../api/admin'
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
} from '../../api/models'
import { useAuthStore } from '../../stores/auth'

export function useModelsPage() {
  const auth = useAuthStore()
  const view = shallowRef<ModelPageView>('endpoints')
  const loading = shallowRef(false)
  const busyId = shallowRef('')
  const error = shallowRef('')
  const success = shallowRef('')
  const endpointDialogOpen = shallowRef(false)
  const editingEndpoint = shallowRef<ModelEndpoint | null>(null)
  const endpoints = ref<ModelEndpoint[]>([])
  const knowledgeBases = ref<KnowledgeBaseRow[]>([])
  const selectedKnowledgeBaseId = shallowRef('')
  const profiles = ref<ProfileCollection | null>(null)
  const lastHealthResult = ref<{ endpoint: ModelEndpoint, result: HealthCheckResult } | null>(null)

  const canManageEndpoints = computed(() => auth.user?.platform_role === 'platform_admin')
  const activeEndpoints = computed(() => endpoints.value.filter(item => item.status === 'active'))

  function clearNotice(): void {
    error.value = ''
    success.value = ''
  }

  async function loadPage(): Promise<void> {
    clearNotice()
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
      if (!knowledgeBases.value.some(item => item.id === selectedKnowledgeBaseId.value))
        selectedKnowledgeBaseId.value = knowledgeBases.value[0]?.id ?? ''
      if (!canManageEndpoints.value)
        view.value = 'profiles'
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '模型配置加载失败'
    }
    finally {
      loading.value = false
    }
  }

  async function loadProfiles(): Promise<void> {
    profiles.value = null
    if (!selectedKnowledgeBaseId.value)
      return
    try {
      profiles.value = await fetchProfiles(selectedKnowledgeBaseId.value)
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Profile 加载失败'
    }
  }

  function openCreateEndpoint(): void {
    editingEndpoint.value = null
    endpointDialogOpen.value = true
  }

  function openEditEndpoint(endpoint: ModelEndpoint): void {
    editingEndpoint.value = endpoint
    endpointDialogOpen.value = true
  }

  async function submitEndpoint(payload: EndpointSubmitPayload): Promise<boolean> {
    clearNotice()
    try {
      if (payload.id) {
        await updateModelEndpoint(payload.id, {
          name: payload.name,
          base_url: payload.base_url,
          allowed_models: payload.allowed_models,
        })
        success.value = '模型端点已更新，健康状态已重置'
      }
      else {
        await createModelEndpoint(payload)
        success.value = '模型端点已登记，请执行真实健康检查'
      }
      endpointDialogOpen.value = false
      endpoints.value = (await fetchModelEndpoints()).items
      return true
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '模型端点保存失败'
      return false
    }
  }

  async function toggleEndpoint(endpoint: ModelEndpoint): Promise<void> {
    clearNotice()
    busyId.value = `endpoint-${endpoint.id}`
    try {
      const status = endpoint.status === 'active' ? 'disabled' : 'active'
      await updateModelEndpoint(endpoint.id, { status })
      success.value = status === 'active' ? '模型端点已启用' : '模型端点已停用'
      endpoints.value = (await fetchModelEndpoints()).items
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '端点状态更新失败'
    }
    finally {
      busyId.value = ''
    }
  }

  async function runHealthCheck(endpoint: ModelEndpoint, modelName: string): Promise<void> {
    clearNotice()
    busyId.value = `health-${endpoint.id}`
    try {
      const result = await checkModelEndpoint(endpoint.id, modelName)
      lastHealthResult.value = { endpoint, result }
      success.value = result.status === 'healthy' ? '真实模型调用成功' : result.error ?? '模型检查失败'
      endpoints.value = (await fetchModelEndpoints()).items
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '模型健康检查失败'
    }
    finally {
      busyId.value = ''
    }
  }

  async function addIngestionProfile(input: { max_chars: number, overlap_chars: number }): Promise<void> {
    if (!selectedKnowledgeBaseId.value)
      return
    clearNotice()
    try {
      await createIngestionProfile({
        knowledge_base_id: Number(selectedKnowledgeBaseId.value),
        max_chars: input.max_chars,
        overlap_chars: input.overlap_chars,
        preserve_locator: true,
      })
      success.value = '切片 Profile 已创建，新上传或重新解析时使用'
      await loadProfiles()
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '切片 Profile 创建失败'
    }
  }

  async function addEmbeddingProfile(input: { endpointId: string, modelName: string, expectedDimension: number | null }): Promise<void> {
    clearNotice()
    try {
      await createEmbeddingProfile({
        model_endpoint_id: Number(input.endpointId),
        model_name: input.modelName,
        expected_dimension: input.expectedDimension,
        normalization: 'l2',
        query_instruction: '',
        document_instruction: '',
      })
      success.value = '嵌入 Profile 已通过真实维度检查并创建'
      await loadProfiles()
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : '嵌入 Profile 创建失败'
    }
  }

  async function addRuntimeProfile(input: { embeddingProfileId: string, generationEndpointId: string, generationModel: string, topK: number, contextMaxChars: number, temperature: number, answerRules: string }): Promise<void> {
    if (!selectedKnowledgeBaseId.value)
      return
    clearNotice()
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
      success.value = 'Runtime Profile 已创建，激活后进入运行链路'
      await loadProfiles()
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Runtime Profile 创建失败'
    }
  }

  async function activateRuntime(id: string): Promise<void> {
    clearNotice()
    busyId.value = `runtime-${id}`
    try {
      const result = await activateRuntimeProfile(id)
      success.value = result.effect_scope === 'rebuild_required'
        ? 'Runtime Profile 已激活；嵌入模型发生变化，请重新构建并发布'
        : 'Runtime Profile 已激活并立即生效'
      await loadProfiles()
    }
    catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'Runtime Profile 激活失败'
    }
    finally {
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
    error,
    success,
    endpointDialogOpen,
    editingEndpoint,
    endpoints,
    activeEndpoints,
    knowledgeBases,
    selectedKnowledgeBaseId,
    profiles,
    lastHealthResult,
    canManageEndpoints,
    loadPage,
    openCreateEndpoint,
    openEditEndpoint,
    submitEndpoint,
    toggleEndpoint,
    runHealthCheck,
    addIngestionProfile,
    addEmbeddingProfile,
    addRuntimeProfile,
    activateRuntime,
  }
}
