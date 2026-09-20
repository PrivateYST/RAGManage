<script setup lang="ts">
import type { ReleaseDetailDialogEmits, ReleaseDetailDialogProps } from './type'
import { FileText, PackageCheck, X } from '@/components'
import { useReleaseDetailDialog } from './index'
import './index.scss'

const props = defineProps<ReleaseDetailDialogProps>()
const emit = defineEmits<ReleaseDetailDialogEmits>()
const { totalChunks, totalEmbeddings, formatDate, shortHash, providerLabel, itemStateLabel }
  = useReleaseDetailDialog(props)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="release-detail-backdrop" @mousedown.self="emit('close')">
      <section
        class="release-detail-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-detail-title"
      >
        <header class="release-detail-header">
          <div class="release-detail-heading">
            <span><PackageCheck :size="18" aria-hidden="true" /></span>
            <div>
              <h2 id="release-detail-title">
                {{ release ? `Release #${release.id}` : 'Release 详情' }}
              </h2>
              <p>查看当前发布版本冻结的文档、向量索引与接入配置。</p>
            </div>
          </div>
          <button
            class="dialog-close-button"
            type="button"
            aria-label="关闭"
            @click="emit('close')"
          >
            <X :size="17" aria-hidden="true" />
          </button>
        </header>

        <div v-if="loading" class="release-detail-loading">
          <span class="loading-spinner" />
          <p>正在读取 Release 清单…</p>
        </div>
        <div v-else-if="error" class="release-detail-error">
          {{ error }}
        </div>
        <div v-else-if="release && detail" class="release-detail-body">
          <section class="release-explanation">
            <strong>发布的是什么？</strong>
            <p>
              发布会把构建 #{{ release.build_id }}
              中的文档版本、切片及向量配置冻结为不可变清单，并切换为知识问答当前检索版本。
            </p>
          </section>

          <section class="release-detail-metrics">
            <article>
              <span>来源构建</span><strong>#{{ release.build_id }}</strong>
            </article>
            <article>
              <span>发布文档</span><strong>{{ detail.items.length }}</strong>
            </article>
            <article>
              <span>切片</span><strong>{{ totalChunks }}</strong>
            </article>
            <article>
              <span>向量</span><strong>{{ totalEmbeddings }}</strong>
            </article>
          </section>

          <section class="release-detail-section">
            <div class="release-detail-section-title">
              <strong>发布配置</strong>
              <span class="status-pill" :class="release.is_active ? 'ready' : 'retired'">{{
                release.is_active ? '当前使用' : '历史版本'
              }}</span>
            </div>
            <dl class="release-detail-config">
              <dt>发布时间</dt>
              <dd>{{ formatDate(release.created_at) }}</dd>
              <dt>嵌入模型</dt>
              <dd>{{ release.model_name }} · {{ release.dimension }} 维</dd>
              <dt>接入方式</dt>
              <dd>
                {{ providerLabel(release.provider) }} · Profile #{{ release.embedding_profile_id }}
              </dd>
              <dt>接入端点</dt>
              <dd>{{ release.base_url }}</dd>
              <dt>模型摘要</dt>
              <dd>{{ shortHash(release.model_revision) }}</dd>
              <dt>配置摘要</dt>
              <dd>{{ shortHash(release.embedding_definition_hash) }}</dd>
              <dt>清单摘要</dt>
              <dd>{{ shortHash(release.manifest_hash) }}</dd>
              <dt>内容世代</dt>
              <dd>Epoch {{ detail.build.input_epoch }}</dd>
            </dl>
          </section>

          <section class="release-detail-section release-document-list">
            <div class="release-detail-section-title">
              <strong>已发布文档</strong><span>{{ detail.items.length }} 份</span>
            </div>
            <div v-if="detail.items.length" class="release-document-table">
              <div class="release-document-row header">
                <span>文档</span><span>版本</span><span>切片</span><span>向量</span><span>状态</span>
              </div>
              <div
                v-for="item in detail.items"
                :key="item.document_id"
                class="release-document-row"
              >
                <span class="release-document-name"><FileText :size="14" aria-hidden="true" />{{ item.title }}</span>
                <span>v{{ item.version_no }}</span>
                <span>{{ item.chunk_count }}</span>
                <span>{{ item.embedded_count }}</span>
                <span class="release-document-state">{{ itemStateLabel(item.state) }}</span>
              </div>
            </div>
            <div v-else class="release-document-empty">
              当前 Release 没有文档。
            </div>
          </section>
        </div>
      </section>
    </div>
  </Teleport>
</template>
