<script setup lang="ts">
import type { IngestionProfilesProps } from './type'
import { FileCog, Plus } from '@/components'
import { effectScopeLabel } from '@/views/models/enum'
import { useIngestionProfileForm } from './index'
import './index.scss'

defineProps<IngestionProfilesProps>()
const emit = defineEmits<{ create: [input: { max_chars: number, overlap_chars: number }] }>()
const { form } = useIngestionProfileForm()
</script>

<template>
  <section class="content-card profile-section">
    <header>
      <div>
        <span><FileCog :size="16" /></span>
        <div>
          <strong>Ingestion Profile</strong><small>解析与切片规则形成不可变版本，新配置用于后续上传或重新解析。</small>
        </div>
      </div>
      <span class="effect-badge rebuild">{{ effectScopeLabel.reparse_required }}</span>
    </header>
    <form
      class="profile-create-row"
      @submit.prevent="
        emit('create', { max_chars: form.maxChars, overlap_chars: form.overlapChars })
      "
    >
      <label>单片最大字符<input v-model.number="form.maxChars" type="number" min="400" max="8000"></label>
      <label>重叠字符<input
        v-model.number="form.overlapChars"
        type="number"
        min="0"
        :max="form.maxChars - 1"
      ></label>
      <button class="secondary-button" type="submit">
        <Plus :size="14" />创建新版本
      </button>
    </form>
    <div class="profile-list">
      <article v-for="item in items" :key="item.id">
        <div>
          <strong>#{{ item.id }} · {{ item.definition.chunking?.max_chars ?? 1800 }} 字符</strong><small>{{ item.definition.parser }} · overlap
            {{ item.definition.chunking?.overlap_chars ?? 0 }}</small>
        </div>
        <code>{{ item.definition_hash.slice(0, 12) }}</code>
      </article>
      <p v-if="!items.length" class="profile-empty">
        尚无切片 Profile，系统仍使用默认 1800 字符规则。
      </p>
    </div>
  </section>
</template>
