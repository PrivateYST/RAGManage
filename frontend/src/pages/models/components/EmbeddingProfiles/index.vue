<script setup lang="ts">
import type { EmbeddingProfilesProps } from './type'
import { Braces, Plus } from 'lucide-vue-next'
import { effectScopeLabel } from '../../enum'
import { useEmbeddingProfileForm } from './index'
import './index.scss'

const props = defineProps<EmbeddingProfilesProps>()
const emit = defineEmits<{ create: [input: { endpointId: string, modelName: string, expectedDimension: number | null }] }>()
const { form, embeddingEndpoints } = useEmbeddingProfileForm(() => props.endpoints)
</script>

<template>
  <section class="content-card profile-section">
    <header><div><span><Braces :size="16" /></span><div><strong>Embedding Profile</strong><small>创建时执行真实向量请求并固化模型 revision、维度和归一化规则。</small></div></div><span class="effect-badge rebuild">{{ effectScopeLabel.rebuild_required }}</span></header>
    <form class="profile-create-row embedding-profile-form" @submit.prevent="emit('create', { endpointId: form.endpointId, modelName: form.modelName, expectedDimension: form.expectedDimension })">
      <label>嵌入端点<select v-model="form.endpointId" required><option v-for="endpoint in embeddingEndpoints" :key="endpoint.id" :value="endpoint.id">{{ endpoint.name }}</option></select></label>
      <label>模型<select v-model="form.modelName" required><option v-for="model in embeddingEndpoints.find(item => item.id === form.endpointId)?.allowed_models ?? []" :key="model" :value="model">{{ model }}</option></select></label>
      <label>期望维度<input v-model.number="form.expectedDimension" type="number" min="1" max="65536"></label>
      <button class="secondary-button" type="submit" :disabled="!embeddingEndpoints.length">
        <Plus :size="14" />实测并创建
      </button>
    </form>
    <div class="profile-list">
      <article v-for="item in items" :key="item.id">
        <div><strong>#{{ item.id }} · {{ item.model_name }} · {{ item.dimension }} 维</strong><small>{{ item.endpoint_name }} · revision {{ item.model_revision.slice(0, 12) }} · {{ item.normalization }}</small></div><code>{{ item.definition_hash.slice(0, 12) }}</code>
      </article>
      <p v-if="!items.length" class="profile-empty">
        尚无可选的嵌入 Profile。
      </p>
    </div>
  </section>
</template>
