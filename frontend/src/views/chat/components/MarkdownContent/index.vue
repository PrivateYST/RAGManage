<script setup lang="ts">
import type { MarkdownContentProps } from './type'
import { useMarkdownContent } from './index'
import './index.scss'

const props = defineProps<MarkdownContentProps>()
const { renderedContent } = useMarkdownContent(() => props.content)
</script>

<template>
  <div class="markdown-content" v-html="renderedContent" />
</template>
