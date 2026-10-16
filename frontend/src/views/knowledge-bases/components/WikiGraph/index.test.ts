/** 图谱回归：共享来源去重、状态过滤、失效证据与稳定布局。 */
import type { WikiEntry } from '@/api/wiki'
import { describe, expect, it } from 'vitest'
import { buildWikiGraph } from './index'

/** 两条词条共享同一文档版本，模拟真实公共卫生规范。 */
function entry(id: string, status: WikiEntry['status'] = 'published'): WikiEntry {
  return {
    id,
    knowledge_base_id: '4',
    term: `词条${id}`,
    definition: '原文定义',
    aliases: ['共用别名'],
    status,
    version_no: 1,
    owner_user_id: '1',
    valid_from: null,
    valid_until: null,
    updated_at: '',
    sources: [
      {
        chunk_id: id,
        document_id: '7',
        document_version_id: '7',
        document_title: '规范',
        version_no: 1,
        locator: { page: 33 },
        content: '原文',
      },
    ],
  }
}

describe('wiki graph', () => {
  it('deduplicates shared documents and aliases while retaining real edges', () => {
    const graph = buildWikiGraph([entry('1'), entry('2')])
    expect(graph.nodes.filter((n) => n.kind === 'document')).toHaveLength(1)
    expect(graph.nodes.filter((n) => n.kind === 'alias')).toHaveLength(1)
    expect(graph.edges).toHaveLength(4)
    expect(graph.nodes.find((n) => n.kind === 'document')?.entries).toHaveLength(2)
    expect(graph).toEqual(buildWikiGraph([entry('1'), entry('2')]))
  })
  it('excludes drafts by default and does not fabricate missing sources', () => {
    expect(buildWikiGraph([entry('1', 'draft')]).nodes).toHaveLength(0)
    expect(buildWikiGraph([entry('1', 'draft')], true).nodes.length).toBeGreaterThan(0)
    const missing = entry('2')
    missing.sources = []
    expect(buildWikiGraph([missing]).nodes.some((n) => n.kind === 'document')).toBe(false)
  })
})
