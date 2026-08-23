import { request } from './http'
import { useUserStore } from '@/stores/user'
import router from '@/router'

/* ===================== 会话 ===================== */

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

/** 会话列表（J 区聊天页数据源） */
export function fetchConversations() {
  return request<Conversation[]>({ url: '/conversations' })
}

/** 创建会话 */
export function createConversation(title?: string) {
  return request<Conversation>({ url: '/conversations', method: 'post', data: { title } })
}

/** 重命名会话 */
export function renameConversation(conversationId: number, title: string) {
  return request<Conversation>({ url: `/conversations/${conversationId}`, method: 'patch', data: { title } })
}

/** 删除会话（含全部消息） */
export function deleteConversation(conversationId: number) {
  return request<null>({ url: `/conversations/${conversationId}`, method: 'delete' })
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

/* ===================== 流式对话（SSE） ===================== */

/**
 * SSE 事件（V0.2 阶段五协议）：
 * - start / delta(seq+content, 深度模式带 node) / tool_call / tool_result
 * - done（超时截断带 truncated+reason="timeout"）
 * - error（code/message/retryable/retry_after，运行失败时带 message_id/conversation_id/run_id）
 * - resync（断点续传缓存已过期，需重新加载完整消息）
 * - memory_saved（对话中写入了新记忆）
 */
export interface SSEEvent {
  type: 'start' | 'delta' | 'tool_call' | 'tool_result' | 'done' | 'error' | 'resync' | 'memory_saved'
  /** delta 递增序号（断点续传断点） */
  seq?: number
  content?: string
  node?: string
  tool?: string
  input?: Record<string, unknown>
  preview?: string
  message_id?: number
  conversation_id?: number
  run_id?: number
  /** done 截断标记（超时返回部分结果） */
  truncated?: boolean
  reason?: string
  /** error 帧 */
  code?: string
  message?: string
  retryable?: boolean
  retry_after?: number
  /** memory_saved */
  summary?: string
  importance?: number
}

/** 解析 SSE 流：按 \n\n 分帧，回调 data: JSON 帧（忽略 :keepalive 注释行 / 异常帧） */
async function consumeSSEStream(body: ReadableStream<Uint8Array>, onEvent: (ev: SSEEvent) => void): Promise<void> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx: number
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const chunk = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const line = chunk.split('\n').find((l) => l.startsWith('data:'))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as SSEEvent)
      } catch {
        /* 忽略异常帧 */
      }
    }
  }
}

/** fetch 可选参数窄类型（streamChat/resumeChat 两处使用） */
interface FetchInit {
  method?: string
  headers?: Record<string, string>
  body?: string | null
  signal?: AbortSignal
}

/** 请求前统一处理 401 登出；请求失败由 onError 回调（AbortError 静默忽略） */
async function guardedFetch(
  input: string,
  init: FetchInit,
  onError: (err: Error) => void
): Promise<Response | null> {
  const user = useUserStore()
  let res: Response
  try {
    res = await fetch(input, init)
  } catch (e) {
    if ((e as Error).name !== 'AbortError') onError(e as Error)
    return null
  }
  if (!res.ok) {
    if (res.status === 401) {
      user.logout()
      router.push({ name: 'login' })
      return null
    }
    onError(new Error(`请求失败（HTTP ${res.status}）`))
    return null
  }
  if (!res.body) {
    onError(new Error('AI 服务无响应'))
    return null
  }
  return res
}

/**
 * 流式对话（SSE）：POST /api/v1/chat，fetch 流式解析 data: JSON 帧。
 * 事件按后端协议：start → delta/tool_call/tool_result → done（失败 error）。
 * 网络中断/HTTP 失败走 onError（由调用方决定重连/续传）。
 */
export async function streamChat(
  payload: {
    content: string
    conversation_id?: number | null
    symbol?: string | number | null
    agent_id?: number | null
    run_type?: string
  },
  handlers: { onEvent?: (ev: SSEEvent) => void; onDone?: () => void; onError?: (err: Error) => void },
  signal?: AbortSignal
): Promise<void> {
  const user = useUserStore()
  const res = await guardedFetch(
    '/api/v1/chat',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${user.token}` },
      body: JSON.stringify(payload),
      signal,
    },
    (err) => handlers.onError?.(err)
  )
  if (!res) return
  const body = res.body
  if (!body) {
    handlers.onError?.(new Error('AI 服务无响应'))
    return
  }
  try {
    await consumeSSEStream(body, (ev) => handlers.onEvent?.(ev))
    handlers.onDone?.()
  } catch (e) {
    if ((e as Error).name !== 'AbortError') handlers.onError?.(e as Error)
  }
}

/**
 * 流式断点续传（SSE）：GET /api/v1/chat/resume?conversation_id=&last_seq=。
 * 后端补发 seq>last_seq 的 delta（不重复不丢失），流已结束则再发 done；
 * 缓存已过期返回 {"type":"resync"}（由调用方重新加载完整消息）。
 */
export async function resumeChat(
  conversationId: number,
  lastSeq: number,
  handlers: { onEvent?: (ev: SSEEvent) => void; onDone?: () => void; onError?: (err: Error) => void },
  signal?: AbortSignal
): Promise<void> {
  const user = useUserStore()
  const res = await guardedFetch(
    `/api/v1/chat/resume?conversation_id=${conversationId}&last_seq=${lastSeq}`,
    { headers: { Authorization: `Bearer ${user.token}` }, signal },
    (err) => handlers.onError?.(err)
  )
  if (!res) return
  const body = res.body
  if (!body) {
    handlers.onError?.(new Error('AI 服务无响应'))
    return
  }
  try {
    await consumeSSEStream(body, (ev) => handlers.onEvent?.(ev))
    handlers.onDone?.()
  } catch (e) {
    if ((e as Error).name !== 'AbortError') handlers.onError?.(e as Error)
  }
}

/* ===================== 交易策略 ===================== */

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

/** 策略列表（M 区 / J 区策略页数据源） */
export function fetchStrategies() {
  return request<Strategy[]>({ url: '/strategies' })
}

/** 保存策略 */
export function createStrategy(payload: {
  title: string
  description?: string
  code?: string
  params?: Record<string, unknown>
  status?: string
}) {
  return request<Strategy>({ url: '/strategies', method: 'post', data: payload })
}

/** 策略详情（N 区） */
export function fetchStrategy(strategyId: number) {
  return request<Strategy>({ url: `/strategies/${strategyId}` })
}

/** 更新策略（N 区编辑代码保存） */
export function updateStrategy(
  strategyId: number,
  patch: Partial<Pick<Strategy, 'title' | 'description' | 'code' | 'params' | 'status'>>
) {
  return request<Strategy>({ url: `/strategies/${strategyId}`, method: 'put', data: patch })
}

/** 删除策略 */
export function deleteStrategy(strategyId: number) {
  return request<null>({ url: `/strategies/${strategyId}`, method: 'delete' })
}

/** AI 生成策略（结构化输出：代码 + JSON 参数） */
export function generateStrategy(description: string, symbol?: string | number) {
  return request<{
    strategy_name?: string
    description?: string
    code?: string
    params?: Record<string, unknown>
    risk_warning?: string
  }>({
    url: '/strategies/generate',
    method: 'post',
    data: { description, symbol },
  })
}

/* ===================== 定制 Agent ===================== */

export interface AgentConfig {
  id: number
  name: string
  agent_type?: string
  system_prompt?: string | null
  tools?: Record<string, unknown> | null
  llm_config?: Record<string, unknown> | null
  memory_config?: Record<string, unknown> | null
  status?: string
  created_at?: string
  updated_at?: string
}

/** 定制 Agent 列表 */
export function fetchAgents() {
  return request<AgentConfig[]>({ url: '/agents' })
}

/** 创建定制 Agent（可指定 template=technical|fundamental|risk_control 从预设创建） */
export function createAgent(payload: {
  name: string
  agent_type?: string
  system_prompt?: string
  tools?: Record<string, unknown>
  llm_config?: Record<string, unknown>
  memory_config?: Record<string, unknown>
  status?: string
  template?: string
}) {
  return request<AgentConfig>({ url: '/agents', method: 'post', data: payload })
}

/** 更新定制 Agent（含启停 status=active|draft） */
export function updateAgent(
  agentId: number,
  patch: Partial<Pick<AgentConfig, 'name' | 'agent_type' | 'system_prompt' | 'tools' | 'llm_config' | 'memory_config' | 'status'>>
) {
  return request<AgentConfig>({ url: `/agents/${agentId}`, method: 'patch', data: patch })
}

/** 删除定制 Agent */
export function deleteAgent(agentId: number) {
  return request<null>({ url: `/agents/${agentId}`, method: 'delete' })
}

/* ===================== 回测 ===================== */

export interface BacktestTask {
  id: number
  strategy_id: number
  symbol_id?: number | null
  period?: string
  status: 'queued' | 'running' | 'success' | 'failed'
  progress?: number
  error?: string | null
  created_at?: string
  updated_at?: string
}

export interface BacktestResult {
  id: number
  task_id?: number
  strategy_id: number
  symbol_id?: number | null
  win_rate?: number | null
  profit_loss_ratio?: number | null
  sharpe?: number | null
  total_buys?: number | null
  total_sells?: number | null
  annual_return?: number | null
  max_drawdown?: number | null
  metrics_json?: Record<string, unknown> | null
  start_ts?: string | null
  end_ts?: string | null
}

/** 发起回测（异步，返回任务） */
export function createBacktest(payload: {
  strategy_id: number
  symbol: string | number
  period?: string
  start?: string
  end?: string
  fill_on?: 'close' | 'open'
}) {
  return request<BacktestTask>({ url: '/backtest', method: 'post', data: payload })
}

/** 回测任务状态（前端轮询） */
export function fetchBacktestTask(taskId: number) {
  return request<BacktestTask>({ url: `/backtest/tasks/${taskId}` })
}

/** 回测任务列表（可按 strategy_id 过滤） */
export function fetchBacktestTasks(strategyId?: number) {
  return request<BacktestTask[]>({ url: '/backtest/tasks', params: strategyId ? { strategy_id: strategyId } : undefined })
}

/** 回测结果列表（按策略，N 区与全景 K 线策略指标数据源） */
export function fetchBacktestResults(strategyId: number) {
  return request<BacktestResult[]>({ url: '/backtest/results', params: { strategy_id: strategyId } })
}

/* ===================== Agent 运行历史（4.8.4，后端接口待补，占位） ===================== */

export interface AgentStep {
  id?: number
  run_id?: number
  step_name: string
  agent_role?: string
  content: string
  meta?: Record<string, unknown> | null
  created_at?: string
}

export interface AgentRun {
  id: number
  agent_id?: number | null
  conversation_id?: number | null
  symbol_id?: number | null
  run_type?: string
  status?: string
  input?: string | null
  output?: string | null
  tokens?: number | null
  error?: string | null
  created_at?: string
}

/**
 * Agent 运行历史列表。后端 GET /api/v1/agent/runs 尚待实现（编排缺失，见 fixed.md），
 * 前端先按约定接入，接口 404 时由调用方展示空态占位。
 */
export function fetchAgentRuns() {
  return request<AgentRun[]>({ url: '/agent/runs', silent: true })
}

/** Agent 运行详情（含 agent_steps） */
export function fetchAgentRunDetail(runId: number) {
  return request<AgentRun & { steps?: AgentStep[] }>({ url: `/agent/runs/${runId}`, silent: true })
}

/* ===================== 记忆文件（4.6，后端接口待补，占位） ===================== */

export interface MemoryFileItem {
  path: string
  content_type?: string
  content?: string
  updated_at?: string
}

/**
 * 本地记忆文件列表。后端 GET /api/v1/memory/files 尚待实现（编排缺失，见 fixed.md），
 * 前端先按约定接入，接口 404 时由调用方展示空态占位。
 */
export function fetchMemoryFiles() {
  return request<MemoryFileItem[]>({ url: '/memory/files', silent: true })
}

/* ===================== 记忆事实（V0.2 阶段六 6.4，M 区记忆文件面板） ===================== */

/** 单条记忆事实（GET /memory/facts 返回项） */
export interface MemoryFact {
  id: number
  content: string
  importance: number
  source_type: string
  source_id?: number | null
  created_at?: string
}

/** 记忆事实分页返回 */
export interface MemoryFactPage {
  items: MemoryFact[]
  total: number
  page: number
  size: number
}

/** 记忆事实列表（分页，可按重要性下限筛选） */
export function fetchMemoryFacts(params: { page?: number; size?: number; importance_min?: number } = {}) {
  return request<MemoryFactPage>({ url: '/memory/facts', params, silent: true })
}

/** 删除单条记忆 */
export function deleteMemoryFact(factId: number) {
  return request<null>({ url: `/memory/facts/${factId}`, method: 'delete', silent: true })
}

/** 清空全部记忆 */
export function clearMemoryFacts() {
  return request<{ deleted: number }>({ url: '/memory/facts', method: 'delete', silent: true })
}

