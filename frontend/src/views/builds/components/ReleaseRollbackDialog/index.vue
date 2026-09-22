<!-- Release 回退属于破坏性版本切换，统一使用 AppConfirmDialog 的 AlertDialog 语义。 -->
<script setup lang="ts">
import type { ReleaseRollbackDialogEmits, ReleaseRollbackDialogProps } from './type'
import { AppConfirmDialog, RotateCcw, TriangleAlert } from '@/components'
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
  <AppConfirmDialog
    :open="open"
    title="回退 Release"
    description="这会切换知识问答使用的检索版本，请确认目标版本和来源校验结果。"
    confirm-label="确认回退"
    content-class="w-[min(560px,calc(100vw-2rem))]"
    :busy="rollingBack"
    @update:open="(value) => !value && handleClose()"
    @confirm="handleConfirm"
  >
    <template #body>
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
              >构建 #{{ targetRelease.build_id }} · {{ targetRelease.document_count }} 份文档</small
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
      </div>
    </template>
    <template #footer>
      <div class="release-rollback-footer">
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
            rollingBack ? '正在回退…' : `确认回退到 #${targetRelease?.id ?? ''}`
          }}
        </button>
      </div>
    </template>
  </AppConfirmDialog>
</template>
