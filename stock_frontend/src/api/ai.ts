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

/** SSE 事件：deep 模式（run_type=diagnose/plan/radar）delta 事件带 node 透传多智能体节点输出 */
export interface SSEEvent {
  type: 'start' | 'delta' | 'tool_call' | 'tool_result' | 'done' | 'error'
  content?: string
  node?: string
  tool?: string
  input?: Record<string, unknown>
  preview?: string
  message_id?: number
  conversation_id?: number
  run_id?: number
}

/**
 * 流式对话（SSE）：POST /api/v1/chat，fetch 流式解析 data: JSON 帧。
 * 事件按后端协议：start → delta/tool_call/tool_result → done（失败 error）。
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
  let res: Response
  try {
    res = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${user.token}` },
      body: JSON.stringify(payload),
      signal,
    })
  } catch (e) {
    if ((e as Error).name !== 'AbortError') handlers.onError?.(e as Error)
    return
  }
  if (!res.ok) {
    if (res.status === 401) {
      user.logout()
      router.push({ name: 'login' })
      return
    }
    handlers.onError?.(new Error(`请求失败（HTTP ${res.status}）`))
    return
  }
  if (!res.body) {
    handlers.onError?.(new Error('AI 服务无响应'))
    return
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  try {
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
          handlers.onEvent?.(JSON.parse(line.slice(5).trim()) as SSEEvent)
        } catch {
          /* 忽略异常帧 */
        }
      }
    }
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

