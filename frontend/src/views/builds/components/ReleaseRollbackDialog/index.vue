<script setup lang="ts">
import type { ReleaseRollbackDialogEmits, ReleaseRollbackDialogProps } from './type'
import { RotateCcw, TriangleAlert, X } from '@/components'
import { useReleaseRollbackDialog } from './index'
import './index.scss'

const props = defineProps<ReleaseRollbackDialogProps>()
const emit = defineEmits<ReleaseRollbackDialogEmits>()
const { canConfirm, providerLabel, handleClose, handleConfirm } = useReleaseRollbackDialog(props, {
  close: () => emit('close'),
  confirm: () => emit('confirm'),
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="release-rollback-backdrop" @mousedown.self="handleClose">
      <section
        class="release-rollback-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="release-rollback-title"
      >
        <header class="release-rollback-header">
          <div class="release-rollback-heading">
            <span><RotateCcw :size="18" aria-hidden="true" /></span>
            <div>
              <h2 id="release-rollback-title">回退 Release</h2>
              <p>将知识问答使用的检索版本切换到历史 Release。</p>
            </div>
          </div>
          <button
            class="dialog-close-button"
            type="button"
            aria-label="关闭"
            :disabled="rollingBack"
            @click="handleClose"
          >
            <X :size="17" aria-hidden="true" />
          </button>
        </header>

        <div v-if="targetRelease && currentRelease" class="release-rollback-body">
          <section class="release-rollback-compare">
            <article>
              <span>当前使用</span>
              <strong>Release #{{ currentRelease.id }}</strong>
              <small
                >构建 #{{ currentRelease.build_id }} ·
                {{ currentRelease.document_count }} 份文档</small
              >
            </article>
            <RotateCcw :size="18" aria-hidden="true" />
            <article class="target">
              <span>回退目标</span>
              <strong>Release #{{ targetRelease.id }}</strong>
              <small
                >构建 #{{ targetRelease.build_id }} ·
                {{ targetRelease.document_count }} 份文档</small
              >
            </article>
          </section>

          <section class="release-rollback-target">
            <div>
              <span>嵌入模型</span
              ><strong>{{ targetRelease.model_name }} · {{ targetRelease.dimension }} 维</strong>
            </div>
            <div>
              <span>接入配置</span
              ><strong
                >{{ providerLabel(targetRelease.provider) }} · Profile #{{
                  targetRelease.embedding_profile_id
                }}</strong
              >
            </div>
          </section>

          <section class="release-rollback-warning">
            <TriangleAlert :size="18" aria-hidden="true" />
            <div>
              <strong>回退前会重新校验来源</strong>
              <p>
                如果目标 Release
                中存在已删除、已停用、撤权或解析产物失效的文档，系统将拒绝回退。成功后，新的问答请求立即使用目标
                Release。
              </p>
            </div>
          </section>

          <footer class="release-rollback-footer">
            <button
              class="secondary-button"
              type="button"
              :disabled="rollingBack"
              @click="handleClose"
            >
              取消
            </button>
            <button
              class="primary-button"
              type="button"
              :disabled="!canConfirm"
              @click="handleConfirm"
            >
              <RotateCcw :size="15" aria-hidden="true" />{{
                rollingBack ? '正在回退…' : `确认回退到 #${targetRelease.id}`
              }}
            </button>
          </footer>
        </div>
      </section>
    </div>
  </Teleport>
</template>
