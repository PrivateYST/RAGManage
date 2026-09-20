<script setup lang="ts">
import type { SearchEvidence, SearchTestResult } from '@/api/search'
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileText,
  Filter,
  GitMerge,
  Hash,
  Layers3,
  MapPin,
  SearchX,
} from '@/components'

const props = defineProps<{
  result: SearchTestResult | null
  searching: boolean
}>()

function stateLabel(state: SearchTestResult['state']): string {
  return {
    completed: '检索完成',
    no_results: '没有结果',
    index_not_ready: '索引未就绪',
    sources_invalid: '来源已失效',
  }[state]
}

function similarityLabel(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function locatorLabel(item: SearchEvidence): string {
  const locator = item.locator
  if (locator.page !== undefined)
    return `第 ${locator.page} 页`
  if (locator.line_start !== undefined)
    return `第 ${locator.line_start}–${locator.line_end ?? locator.line_start} 行`
  if (locator.char_start !== undefined)
    return `字符 ${locator.char_start}–${locator.char_end ?? locator.char_start}`
  return '原文片段'
}

function sectionLabel(item: SearchEvidence): string {
  return item.section_path.length ? item.section_path.join(' / ') : '正文'
}

function timingValue(name: string): string {
  const value = props.result?.timings[name]
  return typeof value === 'number' ? `${value.toFixed(0)} ms` : '—'
}
</script>

<template>
  <section v-if="searching" class="content-card search-result-loading" aria-live="polite">
    <span class="loading-spinner" aria-hidden="true" />
    <div>
      <strong>正在执行正式检索</strong><span>校验当前 Release，并融合向量语义与关键词候选…</span>
    </div>
  </section>

  <section v-else-if="!result" class="content-card search-result-empty">
    <div class="empty-icon">
      <Layers3 :size="20" aria-hidden="true" />
    </div>
    <strong>等待运行检索</strong>
    <span>结果会展示当前 Release、融合排名、相似度、原文定位和上下文入选情况。</span>
  </section>

  <template v-else>
    <section class="content-card search-trace-summary">
      <header>
        <div class="search-state-icon" :class="result.state">
          <CheckCircle2 v-if="result.state === 'completed'" :size="17" aria-hidden="true" />
          <SearchX v-else-if="result.state === 'no_results'" :size="17" aria-hidden="true" />
          <AlertTriangle v-else :size="17" aria-hidden="true" />
        </div>
        <div>
          <strong>{{ stateLabel(result.state) }}</strong>
          <span>{{ result.message }}</span>
        </div>
        <code>Trace #{{ result.trace_id }}</code>
      </header>

      <div class="search-trace-metrics">
        <article>
          <span>当前 Release</span>
          <strong>{{ result.release ? `#${result.release.id}` : '未发布' }}</strong>
          <small>{{ result.release?.model_name ?? '没有可用索引' }}</small>
        </article>
        <article>
          <span>候选证据</span>
          <strong>{{ result.items.length }}</strong>
          <small>{{ result.items.filter((item) => item.context_included).length }} 条进入上下文</small>
        </article>
        <article>
          <span>有效来源</span>
          <strong>{{ result.source_stats?.valid_documents ?? 0 }} /
            {{ result.source_stats?.total_documents ?? 0 }}</strong>
          <small>{{ result.source_stats?.invalid_documents ?? 0 }} 份失效来源已过滤</small>
        </article>
        <article>
          <span>总耗时</span>
          <strong>{{ timingValue('total_ms') }}</strong>
          <small>融合召回 {{ timingValue('hybrid_search_ms') }}</small>
        </article>
      </div>

      <div v-if="result.filters.length" class="search-filter-list">
        <div class="search-filter-title">
          <Filter :size="13" aria-hidden="true" /><strong>强制过滤范围</strong>
        </div>
        <span v-for="filter in result.filters" :key="filter.name">
          {{ filter.name }}：{{ filter.value
          }}<em v-if="filter.filtered_count">过滤 {{ filter.filtered_count }}</em>
        </span>
      </div>
    </section>

    <section v-if="result.items.length" class="search-evidence-section">
      <header class="search-section-heading">
        <div><FileText :size="15" aria-hidden="true" /><strong>候选证据</strong></div>
        <span>向量语义 + 关键词命中经 RRF 融合排序，重复内容已合并</span>
      </header>
      <div class="search-evidence-list">
        <article
          v-for="item in result.items"
          :key="item.chunk_id"
          class="content-card search-evidence-card"
        >
          <div class="search-evidence-rank">
            <Hash :size="12" aria-hidden="true" />{{ item.rank }}
          </div>
          <div class="search-evidence-body">
            <header>
              <div>
                <strong>{{ item.document_title }}</strong>
                <span>v{{ item.version_no }} · {{ sectionLabel(item) }}</span>
              </div>
              <div class="search-score">
                <strong>{{ similarityLabel(item.similarity) }}</strong>
                <span>相似度</span>
              </div>
            </header>
            <p>{{ item.content }}</p>
            <footer>
              <span><MapPin :size="12" aria-hidden="true" />{{ locatorLabel(item) }}</span>
              <span><Clock3 :size="12" aria-hidden="true" />向量排名
                {{ item.vector_rank ?? item.raw_rank }}</span>
              <span v-if="item.lexical_rank" class="lexical-rank-mark">
                <GitMerge :size="12" aria-hidden="true" />关键词排名 {{ item.lexical_rank }}
              </span>
              <span v-if="item.context_included" class="context-mark">证据 {{ item.evidence_no }} · 已进入上下文</span>
              <span v-else>未进入上下文</span>
            </footer>
          </div>
        </article>
      </div>
    </section>

    <details v-if="result.context" class="content-card search-context-preview">
      <summary>查看组装后的模型上下文（{{ result.context.length }} 字符）</summary>
      <pre>{{ result.context }}</pre>
    </details>
  </template>
</template>
