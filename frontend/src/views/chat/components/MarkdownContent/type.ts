export interface MarkdownContentProps {
  content: string
  /** 流式生成期间保持中间态解析，结束后强制收敛未闭合 Markdown 结构。 */
  final?: boolean
}
