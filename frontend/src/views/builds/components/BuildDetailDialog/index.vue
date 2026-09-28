<!-- 构建详情弹窗：展示构建快照及每份文档的处理状态，边界是只读诊断，不触发重试或发布。 -->
<script setup lang="ts">
import type { BuildDetailDialogEmits, BuildDetailDialogProps } from './type'
import { AppDialog, Box, FileText, X } from '@/components'
import './index.scss'

const props = defineProps<BuildDetailDialogProps>()
const emit = defineEmits<BuildDetailDialogEmits>()

function formatDate(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

function shortHash(value: string): string {
  return value.length > 16 ? value.slice(0, 16) : value
}

function providerLabel(value: string): string {
  return value === 'open_webui' ? 'Open WebUI 网关' : value === 'ollama' ? 'Ollama 直连' : value
}

function stateLabel(value: string): string {
  return value === 'completed' ? '构建完成' : value === 'failed' ? '失败' : value
}

function errorMessage(error: Record<string, unknown> | null): string {
  if (!error) return '—'
  return typeof error.message === 'string'
    ? error.message
    : typeof error.code === 'string'
      ? error.code
      : '处理失败'
}

const totalChunks = () => props.detail?.items.reduce((sum, item) => sum + item.chunk_count, 0) ?? 0
const totalEmbedded = () =>
  props.detail?.items.reduce((sum, item) => sum + item.embedded_count, 0) ?? 0
</script>

<template>
  <AppDialog
    :open="open"
    title="构建详情"
    content-class="w-[min(960px,calc(100vw-2rem))]"
    @close="emit('close')"
  >
    <section class="build-detail-dialog">
      <header class="build-detail-header">
        <div class="build-detail-heading">
          <span><Box :size="18" /></span>
          <div>
            <h2>{{ selectedBuild ? `构建 #${selectedBuild.id}` : '构建详情' }}</h2>
            <p>查看构建快照、处理统计与逐文档结果。</p>
          </div>
        </div>
        <button class="dialog-close-button" type="button" aria-label="关闭" @click="emit('close')">
          <X :size="17" />
        </button>
      </header>
      <div v-if="loading" class="build-detail-loading">
        <span class="loading-spinner" />
        <p>正在读取构建清单…</p>
      </div>
      <div v-else-if="error" class="build-detail-error">{{ error }}</div>
      <div v-else-if="detail" class="build-detail-body">
        <section class="build-detail-metrics">
          <article>
            <span>文档</span><strong>{{ detail.items.length }}</strong>
          </article>
          <article>
            <span>切片</span><strong>{{ totalChunks() }}</strong>
          </article>
          <article>
            <span>向量</span><strong>{{ totalEmbedded() }}</strong>
          </article>
          <article>
            <span>状态</span
            ><strong class="status-pill" :class="detail.build.state">{{
              detail.build.state
            }}</strong>
          </article>
        </section>
        <section class="build-detail-section">
          <div class="build-detail-section-title">
            <strong>构建快照</strong><span>{{ formatDate(detail.build.updated_at) }}</span>
          </div>
          <dl class="build-detail-config">
            <dt>内容世代</dt>
            <dd>Epoch {{ detail.build.input_epoch }}</dd>
            <dt>任务</dt>
            <dd>{{ detail.build.task_id }}</dd>
            <dt>嵌入模型</dt>
            <dd>{{ detail.build.model_name }} · {{ detail.build.dimension }} 维</dd>
            <dt>模型摘要</dt>
            <dd>{{ shortHash(detail.build.model_revision) }}</dd>
            <dt>嵌入配置</dt>
            <dd>
              Profile #{{ detail.build.embedding_profile_id }} ·
              {{ providerLabel(detail.build.provider) }}
            </dd>
            <dt>Runtime 快照</dt>
            <dd>{{ detail.build.runtime_profile_id ?? '未绑定' }}</dd>
            <dt>接入端点</dt>
            <dd>{{ detail.build.base_url }}</dd>
            <dt>配置摘要</dt>
            <dd>{{ shortHash(detail.build.embedding_definition_hash) }}</dd>
          </dl>
        </section>
        <section class="build-detail-section">
          <div class="build-detail-section-title">
            <strong>逐文档处理明细</strong><span>{{ detail.items.length }} 份</span>
          </div>
          <div v-if="detail.items.length" class="build-document-table">
            <div class="build-document-row header">
              <span>文档</span><span>版本</span><span>切片</span><span>向量</span><span>状态</span
              ><span>错误</span>
            </div>
            <div v-for="item in detail.items" :key="item.document_id" class="build-document-row">
              <span class="build-document-name"><FileText :size="14" />{{ item.title }}</span
              ><span>v{{ item.version_no }}</span
              ><span>{{ item.chunk_count }}</span
              ><span>{{ item.embedded_count }}</span
              ><span>{{ stateLabel(item.state) }}</span
              ><span class="build-document-error">{{ errorMessage(item.error) }}</span>
            </div>
          </div>
          <div v-else class="build-document-empty">当前构建没有文档处理记录。</div>
        </section>
      </div>
    </section>
  </AppDialog>
</template>
