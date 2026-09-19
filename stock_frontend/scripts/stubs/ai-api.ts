/**
 * G27 验证脚本（scripts/verify-pagination.mjs）专用桩：模拟 `@/api/ai`。
 *
 * 语义与后端 G09 实现保持一致：
 * - 列表 `{items, total, page, size, total_pages}`
 * - 消息 `{items, has_more, next_cursor}`（items 升序，不传 before 取最新 limit 条）
 *
 * 仅供脚本内 esbuild 打包使用，不进入应用产物（src/ 下无任何引用）。
 */

export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  conversation_id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string
}

export const state = {
  conversations: [] as Conversation[],
  /** conversationId → 升序消息 */
  messages: new Map<number, ChatMessage[]>(),
  /** 记录调用，供断言「未重复请求」等行为 */
  messageCalls: [] as Array<{ conversationId: number; limit: number; before?: number }>,
  conversationCalls: [] as Array<{ page: number; size: number }>,
  /** >0 时给 fetchMessages 加延迟，用于验证「加载期间切换会话丢弃结果」 */
  delayMs: 0,
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export function fetchConversations(params: { page?: number; size?: number } = {}) {
  const page = params.page ?? 1
  const size = params.size ?? 20
  state.conversationCalls.push({ page, size })
  const start = (page - 1) * size
  return Promise.resolve({
    items: state.conversations.slice(start, start + size),
    total: state.conversations.length,
    page,
    size,
    total_pages: Math.ceil(state.conversations.length / size),
  })
}

export async function fetchMessages(
  conversationId: number,
  params: { limit?: number; before?: number } = {}
) {
  const limit = params.limit ?? 50
  state.messageCalls.push({ conversationId, limit, before: params.before })
  if (state.delayMs > 0) await sleep(state.delayMs)
  const all = state.messages.get(conversationId) ?? []
  const end = params.before == null ? all.length : all.findIndex((m) => m.id === params.before)
  const start = Math.max(0, end - limit)
  const items = all.slice(start, end)
  return { items, has_more: start > 0, next_cursor: start > 0 ? items[0].id : null }
}

/* ---- 以下为 store 导入但本脚本不涉及的分支，保持模块可解析 ---- */
export function fetchAgents() {
  return Promise.resolve({ items: [], total: 0, page: 1, size: 20, total_pages: 0 })
}
export function fetchStrategies() {
  return Promise.resolve({ items: [], total: 0, page: 1, size: 20, total_pages: 0 })
}
export function createConversation() {
  return Promise.resolve({ id: 0, title: '新会话', created_at: '', updated_at: '' })
}
export function fetchStrategy() {
  return Promise.resolve({ id: 0, title: '' })
}
export function streamChat() {
  return Promise.resolve()
}
export function resumeChat() {
  return Promise.resolve()
}
export function createBacktest() {
  return Promise.resolve({ id: 0 })
}
export function fetchBacktestTask() {
  return Promise.resolve({ id: 0, status: 'success' })
}
export function fetchBacktestResults() {
  return Promise.resolve([])
}
export function fetchAgentRunDetail() {
  return Promise.resolve({ id: 0 })
}
export const AGENT_NODE_ORDER = [] as const

export function backtestBusyNotice() {
  return null
}
