/** 知识图谱数据、确定性力布局及视口交互；现有组件无图谱原语，因此局部使用 SVG。 */
import type { GraphEdge, GraphNode, WikiGraphData, WikiGraphProps } from './type'
import type { WikiEntry } from '@/api/wiki'
import { computed, ref, watch } from 'vue'

/** 从真实关联构图，共享别名和文档版本去重；失效来源不产生虚构节点。 */
export function buildWikiGraph(entries: WikiEntry[], includeUnpublished = false): WikiGraphData {
  const all = entries.filter((e) => includeUnpublished || e.status === 'published')
  const nodes = new Map<string, GraphNode>()
  const edges = new Map<string, GraphEdge>()
  // SVG 力布局上限避免大型库阻塞页面，明确提示而非静默展示为完整图谱。
  const visible = all.slice(0, 60)
  function addNode(id: string, label: string, kind: GraphNode['kind'], entry: WikiEntry) {
    let node = nodes.get(id)
    if (!node) {
      node = { id, label, kind, entries: [], sources: [], x: 0, y: 0 }
      nodes.set(id, node)
    }
    if (!node.entries.some((e) => e.id === entry.id)) node.entries.push(entry)
    return node
  }
  function link(source: string, target: string, kind: GraphEdge['kind']) {
    const id = `${source}:${target}`
    edges.set(id, { id, source, target, kind })
  }
  for (const entry of visible) {
    const id = `entry:${entry.id}`
    const node = addNode(id, entry.term, 'entry', entry)
    node.sources = entry.sources
    for (const alias of entry.aliases.slice(0, 5)) {
      const aliasId = `alias:${alias.normalize('NFKC').toLowerCase()}`
      addNode(aliasId, alias, 'alias', entry)
      link(id, aliasId, 'alias')
    }
    for (const source of entry.sources) {
      if (!source.document_id || !source.document_version_id || !source.chunk_id) continue
      const docId = `doc:${source.document_id}:${source.document_version_id}`
      const doc = addNode(
        docId,
        `${source.document_title} · v${source.version_no}`,
        'document',
        entry,
      )
      if (!doc.sources.some((s) => s.chunk_id === source.chunk_id)) doc.sources.push(source)
      link(docId, id, 'source')
    }
  }
  const list = [...nodes.values()]
  // 固定初始位置和迭代次数，避免每次点击跳动，也不需要持续动画耗电。
  list.forEach((node, i) => {
    const angle = i * 2.399963 // 黄金角用于稳定地分散初始节点。
    const radius = 80 + Math.sqrt(i) * 30
    node.x = 600 + Math.cos(angle) * radius
    node.y = 350 + Math.sin(angle) * radius
  })
  for (let step = 0; step < 100; step++) {
    const delta = new Map(list.map((node) => [node.id, { x: 0, y: 0 }]))
    for (let i = 0; i < list.length; i++) {
      const a = list[i]!
      for (let j = i + 1; j < list.length; j++) {
        const b = list[j]!
        const dx = a.x - b.x
        const dy = a.y - b.y
        const distance = Math.max(15, Math.hypot(dx, dy))
        const force = Math.min(8, 11000 / (distance * distance))
        const ax = delta.get(a.id)!
        const bx = delta.get(b.id)!
        ax.x += (dx / distance) * force
        ax.y += (dy / distance) * force
        bx.x -= (dx / distance) * force
        bx.y -= (dy / distance) * force
      }
    }
    for (const edge of edges.values()) {
      const a = nodes.get(edge.source)!
      const b = nodes.get(edge.target)!
      const dx = b.x - a.x
      const dy = b.y - a.y
      const distance = Math.max(1, Math.hypot(dx, dy))
      const force = (distance - (edge.kind === 'alias' ? 90 : 170)) * 0.018
      const ax = delta.get(a.id)!
      const bx = delta.get(b.id)!
      ax.x += (dx / distance) * force
      ax.y += (dy / distance) * force
      bx.x -= (dx / distance) * force
      bx.y -= (dy / distance) * force
    }
    for (const node of list) {
      const move = delta.get(node.id)!
      node.x = Math.min(1100, Math.max(100, node.x + move.x + (600 - node.x) * 0.003))
      node.y = Math.min(630, Math.max(60, node.y + move.y + (350 - node.y) * 0.003))
    }
  }
  return {
    nodes: list,
    edges: [...edges.values()],
    truncated: all.length > 60 || visible.some((e) => e.aliases.length > 5),
  }
}

/** 搜索、类型过滤与视口只影响浏览，不修改业务词条与检索配置。 */
export function useWikiGraph(props: WikiGraphProps) {
  const query = ref('')
  const includeUnpublished = ref(false)
  const showAliases = ref(true)
  const showLabels = ref(true)
  const selectedId = ref('')
  const scale = ref(1)
  const pan = ref({ x: 0, y: 0 })
  const graph = computed(() =>
    buildWikiGraph(props.entries, props.canManage && includeUnpublished.value),
  )
  const nodeMap = computed(() => new Map(graph.value.nodes.map((n) => [n.id, n])))
  const selected = computed(() => nodeMap.value.get(selectedId.value))
  const matched = computed(() => {
    const text = query.value.trim().toLowerCase()
    return new Set(
      graph.value.nodes.filter((n) => n.label.toLowerCase().includes(text)).map((n) => n.id),
    )
  })
  const shown = computed(() => {
    const ids = new Set(matched.value)
    if (query.value.trim()) {
      for (const edge of graph.value.edges) {
        if (matched.value.has(edge.source)) ids.add(edge.target)
        if (matched.value.has(edge.target)) ids.add(edge.source)
      }
    }
    return graph.value.nodes.filter(
      (n) => ids.has(n.id) && (showAliases.value || n.kind !== 'alias'),
    )
  })
  const lines = computed(() => {
    const ids = new Set(shown.value.map((n) => n.id))
    return graph.value.edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ ...e, a: nodeMap.value.get(e.source)!, b: nodeMap.value.get(e.target)! }))
  })
  const related = computed(() => {
    const ids = new Set([selectedId.value])
    for (const edge of graph.value.edges) {
      if (edge.source === selectedId.value) ids.add(edge.target)
      if (edge.target === selectedId.value) ids.add(edge.source)
    }
    return ids
  })
  const transform = computed(
    () =>
      `translate(${pan.value.x} ${pan.value.y}) translate(600 350) scale(${scale.value}) translate(-600 -350)`,
  )
  /** 重置缩放和平移恢复全图，但保留业务筛选。 */
  function fit() {
    scale.value = 1
    pan.value = { x: 0, y: 0 }
    selectedId.value = ''
  }
  /** 缩放有上下限，防止节点无限消失或超大渲染。 */
  function zoom(amount: number) {
    scale.value = Math.max(0.4, Math.min(3, scale.value + amount))
  }
  /** 滚轮仅在图谱画布生效，弹窗其他内容继续正常滚动。 */
  function wheel(event: WheelEvent) {
    zoom(event.deltaY < 0 ? 0.1 : -0.1)
  }
  let drag: { x: number; y: number; px: number; py: number; factor: number } | null = null
  /** 捕获指针使拖动画布离开边界后仍能正常结束。 */
  function startDrag(event: PointerEvent) {
    if (event.button !== 0) return
    const svg = event.currentTarget as SVGSVGElement
    svg.setPointerCapture(event.pointerId)
    drag = {
      x: event.clientX,
      y: event.clientY,
      px: pan.value.x,
      py: pan.value.y,
      factor: 1200 / svg.getBoundingClientRect().width,
    }
  }
  /** 像素位移转换为 SVG 视口坐标，适配不同窗口宽度。 */
  function moveDrag(event: PointerEvent) {
    if (drag)
      pan.value = {
        x: drag.px + (event.clientX - drag.x) * drag.factor,
        y: drag.py + (event.clientY - drag.y) * drag.factor,
      }
  }
  /** 指针抬起或取消均解除拖动状态。 */
  function stopDrag() {
    drag = null
  }
  watch(graph, () => {
    if (!nodeMap.value.has(selectedId.value)) selectedId.value = ''
  })
  return {
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
  }
}
