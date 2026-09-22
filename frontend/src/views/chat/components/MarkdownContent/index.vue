<script setup lang="ts">
import type { MarkdownContentProps } from './type'
import MarkdownRender from 'markstream-vue'
import 'markstream-vue/index.css'
import './index.scss'

const props = defineProps<MarkdownContentProps>()
</script>

<template>
  <div class="markdown-content">
    <!-- markstream-vue 按流式中间态增量解析，避免半截 code fence/表格破坏聊天布局。 -->
    <MarkdownRender
      :content="props.content"
      mode="chat"
      html-policy="escape"
      :final="props.final ?? true"
      :render-code-blocks-as-pre="false"
      :code-block-props="{ showCopyButtons: true }"
    />
  </div>
</template>
