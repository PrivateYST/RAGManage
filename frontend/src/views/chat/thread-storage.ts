/** 问答线程的浏览器持久化；对外只保存后端生成的 opaque conversation ID。 */
const THREAD_ID_PREFIX = 'ragmanage:chat:thread:'

export function getThreadId(knowledgeBaseId: string): string | null {
  if (!knowledgeBaseId) return null
  return localStorage.getItem(`${THREAD_ID_PREFIX}${knowledgeBaseId}`)
}

export function setThreadId(knowledgeBaseId: string, threadId: string): void {
  if (knowledgeBaseId && threadId)
    localStorage.setItem(`${THREAD_ID_PREFIX}${knowledgeBaseId}`, threadId)
}

export function deleteThreadId(knowledgeBaseId: string): void {
  if (knowledgeBaseId) localStorage.removeItem(`${THREAD_ID_PREFIX}${knowledgeBaseId}`)
}
