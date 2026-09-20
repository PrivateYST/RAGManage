import DOMPurify from 'dompurify'
import MarkdownIt from 'markdown-it'
import { computed } from 'vue'

const markdown = new MarkdownIt({
  html: false,
  breaks: true,
  linkify: false,
  typographer: false,
})
const sanitizerRootPattern = /^<div><\/div>/

const allowedTags = [
  'div',
  'p',
  'br',
  'strong',
  'em',
  'del',
  'h1',
  'h2',
  'h3',
  'h4',
  'h5',
  'h6',
  'ul',
  'ol',
  'li',
  'blockquote',
  'code',
  'pre',
  'hr',
  'table',
  'thead',
  'tbody',
  'tr',
  'th',
  'td',
]

export function renderMarkdown(content: string): string {
  const sanitized = DOMPurify.sanitize(`<div></div>${markdown.render(content)}`, {
    ALLOWED_TAGS: allowedTags,
    ALLOWED_ATTR: [],
  })
  return sanitized.replace(sanitizerRootPattern, '')
}

export function useMarkdownContent(content: () => string) {
  const renderedContent = computed(() => renderMarkdown(content()))
  return { renderedContent }
}
