<script setup lang="ts">
import type { RuntimeProfilesProps } from './type'
import { Play, Plus, SlidersHorizontal } from '@/components'
import { effectScopeLabel } from '@/views/models/enum'
import { useRuntimeProfileForm } from './index'
import './index.scss'

const props = defineProps<RuntimeProfilesProps>()
const emit = defineEmits<{
  create: [
    input: {
      embeddingProfileId: string
      generationEndpointId: string
      generationModel: string
      topK: number
      contextMaxChars: number
      temperature: number
      answerRules: string
    },
  ]
  activate: [id: string]
}>()
const { form, generationEndpoints } = useRuntimeProfileForm(() => props.endpoints)
</script>

<template>
  <section class="content-card profile-section runtime-section">
    <header>
      <div>
        <span><SlidersHorizontal :size="16" /></span>
        <div>
          <strong>Runtime Profile</strong
          ><small>把检索、生成和回答规则固定为一次运行快照；激活后问答使用该版本。</small>
        </div>
      </div>
      <span class="effect-badge rebuild">换嵌入需重建</span>
    </header>
    <form
      class="runtime-form"
      @submit.prevent="
        emit('create', {
          embeddingProfileId: form.embeddingProfileId,
          generationEndpointId: form.generationEndpointId,
          generationModel: form.generationModel,
          topK: form.topK,
          contextMaxChars: form.contextMaxChars,
          temperature: form.temperature,
          answerRules: form.answerRules,
        })
      "
    >
      <label
        >嵌入 Profile<select v-model="form.embeddingProfileId" required>
          <option value="" disabled>请选择</option>
          <option v-for="profile in embeddingProfiles" :key="profile.id" :value="profile.id">
            #{{ profile.id }} · {{ profile.model_name }} · {{ profile.dimension }} 维
          </option>
        </select></label
      >
      <label
        >生成端点<select v-model="form.generationEndpointId" required>
          <option v-for="endpoint in generationEndpoints" :key="endpoint.id" :value="endpoint.id">
            {{ endpoint.name }}
          </option>
        </select></label
      >
      <label
        >生成模型<select v-model="form.generationModel" required>
          <option
            v-for="model in generationEndpoints.find(
              (item) => item.id === form.generationEndpointId,
            )?.allowed_models ?? []"
            :key="model"
            :value="model"
          >
            {{ model }}
          </option>
        </select></label
      >
      <div class="runtime-number-grid">
        <label>召回 Top K<input v-model.number="form.topK" type="number" min="1" max="20" /></label
        ><label
          >上下文字符<input
            v-model.number="form.contextMaxChars"
            type="number"
            min="1000"
            max="30000" /></label
        ><label
          >温度<input v-model.number="form.temperature" type="number" min="0" max="2" step="0.1"
        /></label>
      </div>
      <label>回答规则<textarea v-model="form.answerRules" maxlength="2000" /></label>
      <button
        class="secondary-button"
        type="submit"
        :disabled="!embeddingProfiles.length || !generationEndpoints.length"
      >
        <Plus :size="14" />创建 Runtime 版本
      </button>
    </form>
    <div class="profile-list runtime-list">
      <article v-for="item in items" :key="item.id">
        <div>
          <strong
            >#{{ item.id }} · {{ item.definition.generation?.model }} · Top
            {{ item.definition.retrieval?.top_k }}</strong
          ><small
            >Embedding #{{ item.embedding_profile_id }} · 上下文
            {{ item.definition.retrieval?.context_max_chars }} 字符 · 温度
            {{ item.definition.generation?.temperature }}</small
          >
        </div>
        <div class="runtime-actions">
          <span v-if="item.active" class="effect-badge immediate">{{
            effectScopeLabel.immediate
          }}</span
          ><button
            v-else
            type="button"
            :disabled="busyId === `runtime-${item.id}`"
            @click="emit('activate', item.id)"
          >
            <Play :size="13" />激活
          </button>
        </div>
      </article>
      <p v-if="!items.length" class="profile-empty">
        尚无 Runtime Profile。创建并激活后，问答链路才会使用这些参数。
      </p>
    </div>
  </section>
</template>
