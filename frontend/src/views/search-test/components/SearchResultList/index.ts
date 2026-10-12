import type { SearchEvidence, SearchTestResult } from '@/api/search'

/** 提供结果卡片使用的状态、相似度、定位及耗时格式化函数。 */
export function useSearchResultList(result: () => SearchTestResult | null) {
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
    if (locator.page !== undefined) return `第 ${locator.page} 页`
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
    const value = result()?.timings[name]
    return typeof value === 'number' ? `${value.toFixed(0)} ms` : '—'
  }

  return { stateLabel, similarityLabel, locatorLabel, sectionLabel, timingValue }
}
