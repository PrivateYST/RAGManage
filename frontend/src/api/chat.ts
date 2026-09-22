/** 问答 API 契约：集中维护会话、运行、流式事件和反馈请求，页面不直接拼接接口细节。 */
import { apiRequest } from './client'

const SSE_BLOCK_SEPARATOR = /\r?\n\r?\n/
const SSE_LINE_SEPARATOR = /\r?\n/

export type RunState = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
export type RunOutcome = 'answered' | 'no_answer' | 'source_conflict' | 'index_not_ready' | null

export interface ConversationRow {
  id: string
  tenant_id: string
  knowledge_base_id: string
  title: string
  status: string
  message_count: number
  created_at: string
  updated_at: string
}

export interface Citation {
  evidence_no: number
  chunk_id: string
  document_id: string
  document_title: string
  document_version_id: string
  version_no: number
  locator: Record<string, number>
  section_path: string[]
  content: string
  source_path: string
}

export interface ChatMessageRow {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  state: string
  release_id: string | null
  created_at: string
  run_id: string | null
  run_state?: RunState
  outcome?: RunOutcome
  hidden: boolean
  citations: Citation[]
  feedback_rating: 'helpful' | 'not_helpful' | null
  feedback_reason: string | null
}

export interface ConversationDetail {
  conversation: {
    id: string
    tenant_id: string
    knowledge_base_id: string
    knowledge_base_name: string
    title: string
    status: string
    active_release_id: string | null
  }
  messages: ChatMessageRow[]
}

export interface GenerationRun {
  id: string
  tenant_id: string
  knowledge_base_id: string
  conversation_id: string
  user_message_id: string
  assistant_message_id: string
  release_id: string | null
  request_id: string
  state: RunState
  outcome: RunOutcome
  cancel_requested: boolean
  error: { code?: string } | null
  question?: string
  answer?: string
  message_state?: string
  hidden?: boolean
  citations?: Citation[]
  created_at: string
  updated_at: string
}

export interface SseMessage {
  event: string
  data: Record<string, unknown>
}

export function consumeSseChunk(
  buffer: string,
  chunk: string,
): { events: SseMessage[]; rest: string } {
  const combined = buffer + chunk
  const blocks = combined.split(SSE_BLOCK_SEPARATOR)
  const rest = blocks.pop() ?? ''
  const events: SseMessage[] = []
  for (const block of blocks) {
    let event = 'message'
    const dataLines: string[] = []
    for (const line of block.split(SSE_LINE_SEPARATOR)) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
    }
    if (!dataLines.length) continue
    events.push({ event, data: JSON.parse(dataLines.join('\n')) as Record<string, unknown> })
  }
  return { events, rest }
}

export function fetchConversations(knowledgeBaseId: string): Promise<{ items: ConversationRow[] }> {
  return apiRequest(
    `/api/v1/conversations?knowledge_base_id=${encodeURIComponent(knowledgeBaseId)}`,
  )
}

export function createConversation(knowledgeBaseId: string): Promise<ConversationRow> {
  return apiRequest('/api/v1/conversations', {
    method: 'POST',
    body: JSON.stringify({ knowledge_base_id: Number(knowledgeBaseId), title: '新会话' }),
  })
}

/**
 * 软删除问答会话；服务端保留消息和审计记录，同时从活动会话列表中移除。
 * 对外使用 public conversation ID，避免前端接触数据库内部主键。
 */
export function deleteConversation(conversationId: string): Promise<void> {
  return apiRequest(`/api/v1/conversations/${encodeURIComponent(conversationId)}`, {
    method: 'DELETE',
  })
}

export function fetchConversation(conversationId: string): Promise<ConversationDetail> {
  return apiRequest(`/api/v1/conversations/${encodeURIComponent(conversationId)}`)
}

export function createRun(
  conversationId: string,
  question: string,
  requestId: string,
): Promise<GenerationRun> {
  return apiRequest(`/api/v1/conversations/${encodeURIComponent(conversationId)}/runs`, {
    method: 'POST',
    body: JSON.stringify({ question, request_id: requestId }),
  })
}

export function fetchRun(runId: string): Promise<GenerationRun> {
  return apiRequest(`/api/v1/runs/${encodeURIComponent(runId)}`)
}

export function cancelRun(runId: string): Promise<GenerationRun> {
  return apiRequest(`/api/v1/runs/${encodeURIComponent(runId)}/cancel`, { method: 'POST' })
}

export function retryRun(runId: string, requestId: string): Promise<GenerationRun> {
  return apiRequest(`/api/v1/runs/${encodeURIComponent(runId)}/retry`, {
    method: 'POST',
    body: JSON.stringify({ request_id: requestId }),
  })
}

export function saveMessageFeedback(
  messageId: string,
  rating: 'helpful' | 'not_helpful',
): Promise<void> {
  return apiRequest(`/api/v1/messages/${encodeURIComponent(messageId)}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating }),
  })
}

export async function streamRun(
  runId: string,
  onEvent: (event: SseMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/v1/runs/${encodeURIComponent(runId)}/events`, {
    credentials: 'include',
    headers: { Accept: 'text/event-stream' },
    signal,
  })
  if (!response.ok || !response.body) throw new Error(`流式请求失败（${response.status}）`)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    const parsed = consumeSseChunk(buffer, decoder.decode(value, { stream: true }))
    buffer = parsed.rest
    parsed.events.forEach(onEvent)
  }
  const tail = consumeSseChunk(buffer, '\n\n')
  tail.events.forEach(onEvent)
}
