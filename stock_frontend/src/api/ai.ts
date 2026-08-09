import { request } from './http'

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
  symbol_id?: number | null
  content: string
  tokens?: number | null
  created_at: string
}

export interface Strategy {
  id: number
  title: string
  description?: string | null
  code?: string | null
  params?: Record<string, unknown> | null
  status?: string
  created_at?: string
  updated_at?: string
}

/** 会话列表（J 区数据源） */
export function fetchConversations() {
  return request<Conversation[]>({ url: '/conversations' })
}

/** 创建会话 */
export function createConversation(title?: string) {
  return request<Conversation>({ url: '/conversations', method: 'post', data: { title } })
}

/** 拉取会话消息（时间升序） */
export function fetchMessages(conversationId: number) {
  return request<ChatMessage[]>({ url: `/conversations/${conversationId}/messages` })
}

/** 追加消息 */
export function sendMessage(
  conversationId: number,
  payload: { role: string; content: string; symbol?: string | number; tokens?: number }
) {
  return request<ChatMessage>({
    url: `/conversations/${conversationId}/messages`,
    method: 'post',
    data: payload,
  })
}

/** 交易策略列表（M 区数据源） */
export function fetchStrategies() {
  return request<Strategy[]>({ url: '/strategies' })
}
