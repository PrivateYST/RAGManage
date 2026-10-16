<!-- 图谱浏览：真实来源与别名关系、局部聚焦及可追溯原文，画布不改变事实。 -->
<script setup lang="ts">
import type { WikiGraphProps } from './type'
import { statusLabels } from '../WikiEntryList/index'
import { useWikiGraph } from './index'
const props = defineProps<WikiGraphProps>()
const emit = defineEmits<{ edit: [entry: import('@/api/wiki').WikiEntry] }>()
const {
  query,
  includeUnpublished,
  showAliases,
  showLabels,
  selectedId,
  selected,
  graph,
  shown,
  lines,
  related,
  transform,
  scale,
  fit,
  zoom,
  wheel,
  startDrag,
  moveDrag,
  stopDrag,
} = useWikiGraph(props)
</script>
<template>
  <div class="flex min-h-0 flex-1 flex-col gap-[12px]">
    <div class="flex flex-wrap items-center gap-[12px]">
      <input
        v-model="query"
        aria-label="搜索图谱节点"
        placeholder="搜索词条、别名或文档…"
        class="h-[36px] w-[260px] rounded-md border border-input bg-background px-[12px] text-sm"
      />
      <label class="flex items-center gap-[6px] text-xs"
        ><input v-model="showAliases" type="checkbox" />显示别名</label
      >
      <label class="flex items-center gap-[6px] text-xs"
        ><input v-model="showLabels" type="checkbox" />显示标签</label
      >
      <label v-if="canManage" class="flex items-center gap-[6px] text-xs"
        ><input v-model="includeUnpublished" type="checkbox" />包含未发布词条</label
      >
      <span class="text-xs text-muted-foreground"
        >{{ shown.length }} / {{ graph.nodes.length }} 个节点 · {{ lines.length }} 条关系</span
      >
    </div>
    <p v-if="graph.truncated" role="status" class="m-0 text-xs text-muted-foreground">
      当前最多显示60个词条，每条最多5个别名；可在列表查看完整数据。
    </p>
    <div
      class="relative grid min-h-0 flex-1 grid-cols-1 overflow-hidden rounded-lg border border-border lg:grid-cols-[1fr_260px]"
    >
      <div class="relative min-h-[220px] min-w-0 overflow-hidden bg-background">
        <svg
          class="h-full w-full touch-none"
          viewBox="0 0 1200 700"
          aria-label="知识关系图谱"
          @wheel.prevent="wheel"
          @pointerdown="startDrag"
          @pointermove="moveDrag"
          @pointerup="stopDrag"
          @pointercancel="stopDrag"
        >
          <g :transform="transform">
            <!-- 共享原文形成淡色分组，分组仅表达来源，不推测额外实体关系。 -->
            <circle
              v-for="node in shown.filter((n) => n.kind === 'document')"
              :key="`cluster:${node.id}`"
              :cx="node.x"
              :cy="node.y"
              r="230"
              fill="var(--secondary)"
              opacity="0.35"
            />
            <line
              v-for="edge in lines"
              :key="edge.id"
              :x1="edge.a.x"
              :y1="edge.a.y"
              :x2="edge.b.x"
              :y2="edge.b.y"
              stroke="var(--border)"
              :stroke-width="
                selectedId && (edge.source === selectedId || edge.target === selectedId) ? 2 : 1
              "
              :opacity="
                selectedId && edge.source !== selectedId && edge.target !== selectedId ? 0.2 : 0.8
              "
            >
              <title>{{ edge.kind === 'source' ? '原文来源' : '别名关系' }}</title>
            </line>
            <g
              v-for="node in shown"
              :key="node.id"
              :transform="`translate(${node.x} ${node.y})`"
              role="button"
              tabindex="0"
              :aria-label="node.label"
              :aria-pressed="selectedId === node.id"
              class="wiki-graph-node cursor-pointer outline-none focus:opacity-70"
              :opacity="selectedId && !related.has(node.id) ? 0.25 : 1"
              @pointerdown.stop
              @click="selectedId = node.id"
              @keydown.enter.prevent="selectedId = node.id"
              @keydown.space.prevent="selectedId = node.id"
            >
              <circle
                :r="node.kind === 'document' ? 12 : node.kind === 'entry' ? 8 : 5"
                :fill="
                  node.kind === 'document'
                    ? '#4D83C7'
                    : node.kind === 'entry'
                      ? '#2F9B8F'
                      : '#DC8A35'
                "
                :stroke="selectedId === node.id ? 'var(--foreground)' : 'var(--background)'"
                :stroke-width="selectedId === node.id ? 3 : 2"
              />
              <text
                v-if="showLabels || selectedId === node.id"
                y="25"
                text-anchor="middle"
                fill="var(--foreground)"
                font-size="12"
                :font-weight="node.kind === 'document' ? 600 : 400"
              >
                {{ node.label.length > 16 ? `${node.label.slice(0, 16)}…` : node.label }}
              </text>
              <title>{{ node.label }}</title>
            </g>
          </g>
        </svg>
        <p
          v-if="!shown.length"
          class="absolute inset-0 flex items-center justify-center text-sm text-muted-foreground"
        >
          {{
            graph.nodes.length
              ? '没有匹配节点，请更换关键词。'
              : '暂无可展示词条，可生成草稿或切换包含未发布词条。'
          }}
        </p>
        <div
          class="absolute bottom-[12px] left-[12px] flex items-center gap-[6px] rounded-md border border-border bg-card p-[6px]"
        >
          <button class="secondary-button" aria-label="缩小图谱" @click="zoom(-0.2)">−</button
          ><span class="px-[6px] text-xs">{{ Math.round(scale * 100) }}%</span
          ><button class="secondary-button" aria-label="放大图谱" @click="zoom(0.2)">＋</button
          ><button class="secondary-button" @click="fit">适应屏幕</button>
        </div>
      </div>
      <aside
        class="min-h-0 overflow-y-auto border-t border-border bg-card p-[16px] lg:border-l lg:border-t-0"
        aria-label="图谱节点详情"
      >
        <div class="mb-[20px] flex flex-wrap gap-[10px] text-xs">
          <span class="text-[#4D83C7]">● 文档版本</span><span class="text-[#2F9B8F]">● 词条</span
          ><span class="text-[#DC8A35]">● 别名</span>
        </div>
        <template v-if="selected">
          <h3 class="m-0 break-words text-sm font-semibold">{{ selected.label }}</h3>
          <p class="text-xs text-muted-foreground">关联 {{ selected.entries.length }} 个词条</p>
          <section
            v-for="entry in selected.entries"
            :key="entry.id"
            class="mt-[16px] border-t border-border pt-[12px]"
          >
            <strong class="text-sm">{{ entry.term }}</strong>
            <p class="text-xs text-muted-foreground">
              {{ statusLabels[entry.status] }} · v{{ entry.version_no }}
            </p>
            <p class="whitespace-pre-wrap text-xs leading-relaxed">{{ entry.definition }}</p>
            <div class="grid gap-[8px]">
              <RouterLink
                v-for="source in entry.sources"
                :key="source.chunk_id"
                :to="{
                  path: '/documents',
                  query: {
                    knowledge_base_id: entry.knowledge_base_id,
                    document_id: source.document_id,
                    version_id: source.document_version_id,
                    chunk_id: source.chunk_id,
                  },
                }"
                class="text-xs text-primary"
                >{{ source.document_title }} ·
                {{
                  source.locator?.page ? `第 ${source.locator.page} 页` : `片段 ${source.chunk_id}`
                }}</RouterLink
              >
            </div>
            <button
              v-if="canManage"
              class="secondary-button mt-[12px]"
              @click="emit('edit', entry)"
            >
              编辑词条
            </button>
          </section>
        </template>
        <p v-else class="text-xs leading-relaxed text-muted-foreground">
          点击节点查看定义、版本与原文。拖动画布移动，滚轮缩放。连线表示真实来源或别名关联，共享文档的词条形成分组。
        </p>
      </aside>
    </div>
  </div>
</template>
<style scoped src="./index.scss" lang="scss"></style>
