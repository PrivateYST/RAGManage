<script setup lang="ts">
import type { ReleaseDiffDialogProps } from './type'
import { CheckCircle2, GitCompareArrows, Rocket, TriangleAlert, X } from '@/components'
import { useReleaseDiffDialog } from './index'
import './index.scss'

const props = defineProps<ReleaseDiffDialogProps>()
const emit = defineEmits<{ close: []; publish: [] }>()

const {
  canPublish,
  changedItems,
  configChanged,
  shortHash,
  providerLabel,
  changeLabel,
  handleClose,
  handlePublish,
} = useReleaseDiffDialog(props, {
  close: () => emit('close'),
  publish: () => emit('publish'),
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="release-diff-backdrop" @mousedown.self="handleClose">
      <section
        class="release-diff-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-diff-title"
      >
        <header class="release-diff-header">
          <div class="release-diff-heading">
            <span><GitCompareArrows :size="18" aria-hidden="true" /></span>
            <div>
              <h2 id="release-diff-title">发布前检查</h2>
              <p>校验候选构建，并比较当前 Release 的文档与模型配置。</p>
            </div>
          </div>
          <button
            class="dialog-close-button"
            type="button"
            aria-label="关闭"
            :disabled="publishing"
            @click="handleClose"
          >
            <X :size="17" aria-hidden="true" />
          </button>
        </header>

        <div v-if="loading" class="release-diff-loading">
          <span class="loading-spinner" />
          <p>正在校验构建与生成差异…</p>
        </div>

        <div v-else-if="preview" class="release-diff-body">
          <section class="release-compare-grid">
            <article>
              <span>当前 Release</span>
              <strong>{{
                preview.current_release ? `Release #${preview.current_release.id}` : '尚未发布'
              }}</strong>
              <small v-if="preview.current_release"
                >构建 #{{ preview.current_release.build_id }}</small
              >
              <small v-else>本次将创建首个发布版本</small>
            </article>
            <article class="candidate">
              <span>候选构建</span>
              <strong>构建 #{{ preview.build.id }}</strong>
              <small>{{ preview.build.knowledge_base_name }}</small>
            </article>
          </section>

          <section
            class="release-validation"
            :class="preview.validation.ready ? 'ready' : 'failed'"
          >
            <CheckCircle2 v-if="preview.validation.ready" :size="17" aria-hidden="true" />
            <TriangleAlert v-else :size="17" aria-hidden="true" />
            <div>
              <strong>{{
                preview.validation.ready ? '发布前校验通过' : '发布前校验未通过'
              }}</strong>
              <p v-if="preview.validation.ready">文档、切片、向量、维度和空间范围均完整一致。</p>
              <ul v-else>
                <li
                  v-for="item in preview.validation.errors"
                  :key="`${item.code}-${item.document_id ?? ''}`"
                >
                  {{ item.title ? `${item.title}：` : '' }}{{ item.message }}
                </li>
              </ul>
            </div>
          </section>

          <section class="release-diff-counts">
            <article class="added">
              <span>新增</span><strong>{{ preview.diff.counts.added }}</strong>
            </article>
            <article class="updated">
              <span>更新</span><strong>{{ preview.diff.counts.updated }}</strong>
            </article>
            <article class="removed">
              <span>移除</span><strong>{{ preview.diff.counts.removed }}</strong>
            </article>
            <article>
              <span>未变化</span><strong>{{ preview.diff.counts.unchanged }}</strong>
            </article>
          </section>

          <section class="release-config-compare">
            <div class="release-section-title">
              <strong>模型与接入配置</strong>
              <span :class="configChanged ? 'changed' : 'same'">{{
                configChanged ? '配置有变化' : '配置未变化'
              }}</span>
            </div>
            <div class="release-config-grid">
              <span>候选 Profile</span
              ><strong
                >#{{ preview.build.embedding_profile_id }} ·
                {{ shortHash(preview.build.embedding_definition_hash) }}</strong
              >
              <span>接入方式</span><strong>{{ providerLabel(preview.build.provider) }}</strong>
              <span>网关端点</span><strong>{{ preview.build.base_url }}</strong>
              <span>嵌入模型</span
              ><strong>{{ preview.build.model_name }} · {{ preview.build.dimension }} 维</strong>
              <span>模型摘要</span><strong>{{ shortHash(preview.build.model_revision) }}</strong>
              <span>清单摘要</span><strong>{{ shortHash(preview.build.manifest_hash) }}</strong>
            </div>
          </section>

          <section v-if="changedItems.length" class="release-document-diff">
            <div class="release-section-title">
              <strong>文档差异</strong><span>{{ changedItems.length }} 项变化</span>
            </div>
            <div class="release-diff-list">
              <div v-for="item in changedItems" :key="item.document_id">
                <span class="change-badge" :class="item.change">{{
                  changeLabel(item.change)
                }}</span>
                <strong>{{ item.title }}</strong>
                <small>v{{ item.from_version ?? '—' }} → v{{ item.to_version ?? '—' }}</small>
              </div>
            </div>
          </section>

          <footer class="release-diff-footer">
            <p>发布后，问答检索将固定使用这个不可变 Release。</p>
            <div>
              <button
                class="secondary-button"
                type="button"
                :disabled="publishing"
                @click="handleClose"
              >
                取消
              </button>
              <button
                class="primary-button"
                type="button"
                :disabled="!canPublish"
                @click="handlePublish"
              >
                <Rocket :size="15" aria-hidden="true" />{{ publishing ? '正在发布…' : '确认发布' }}
              </button>
            </div>
          </footer>
        </div>
      </section>
    </div>
  </Teleport>
</template>
