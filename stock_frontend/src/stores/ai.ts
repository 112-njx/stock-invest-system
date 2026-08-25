import { defineStore } from 'pinia'
import type { SymbolInfo } from '@/api/market'
import {
  fetchAgents,
  fetchConversations,
  fetchMessages,
  fetchStrategies,
  createConversation as apiCreateConversation,
  fetchStrategy,
  resumeChat,
  streamChat,
  createBacktest,
  fetchBacktestResults,
  fetchBacktestTask,
  AGENT_NODE_ORDER,
  type AgentConfig,
  type AgentStep,
  type BacktestResult,
  type ChatMessage,
  type Conversation,
  type SSEEvent,
  type Strategy,
  type TimelineNode,
} from '@/api/ai'

/** 卡片类型：创建交易策略 / 诊断符号 / 交易计划 / 机会雷达 */
export type QuickCardType = 'create' | 'diagnose' | 'plan' | 'radar'
/** 对话区展示模式：chat=聊天(K+L)，strategy=N区策略详情 */
export type AiPanelMode = 'chat' | 'strategy'
/** 流式连接状态：idle / streaming（正常接收）/ reconnecting（断线自动重连）/ manual（需点击继续） */
export type StreamStatus = 'idle' | 'streaming' | 'reconnecting' | 'manual'

/** 流式对话载荷（AIView.send 与重试共用） */
export interface StreamChatPayload {
  content: string
  conversation_id?: number | null
  symbol?: string | number | null
  agent_id?: number | null
  run_type?: string
}

/* ---------- 模块级非响应式流式控制 ---------- */
/** 当前流 AbortController（切换会话/卸载时中止） */
let streamAbort: AbortController | null = null
/** 流代次：每次新流 +1，异步续传步骤校验代次避免旧流继续改状态 */
let streamToken = 0
/** RATE_LIMITED 倒计时定时器 */
let retryTimer: number | null = null
/** memory_saved 轻量提示定时器 */
let memoryTimer: number | null = null

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

/** AI 策略输出后的操作信息（4.5：保存交易策略 / 回测显示） */
export interface StrategyOutputInfo {
  conversationId: number
  /** 用户发送的原始描述（保存策略用） */
  description: string
  /** 是否选择标的（未选择时按钮文案为「保存该交易策略到回测页面」） */
  hasSymbol: boolean
  /** 发送时选中的标的 id（7.5 自动回测用） */
  symbolId?: number | null
  /** 发送时选中的标的代码（7.5 查看详情跳转用） */
  symbolCode?: string | null
}

export const useAiStore = defineStore('ai', {
  state: () => ({
    /* ---------- 会话 ---------- */
    conversations: [] as Conversation[],
    activeConversationId: null as number | null,
    /** 当前会话历史消息（不含流式增量） */
    messages: [] as ChatMessage[],
    /** 对话区模式：chat / strategy（点击策略切 N 区） */
    mode: 'chat' as AiPanelMode,
    /** 当前展示的策略（N 区） */
    activeStrategy: null as Strategy | null,

    /* ---------- 策略 / Agent ---------- */
    strategies: [] as Strategy[],
    agents: [] as AgentConfig[],

    /* ---------- 输入区 ---------- */
    inputText: '',
    selectedSymbol: null as SymbolInfo | null,
    /** 0 表示系统 Agent，>0 为定制 Agent id */
    selectedAgentId: 0 as number | null,
    /** 深度分析模式（4.8.1）：开启后普通输入也走 LangGraph 多智能体 */
    deepMode: false,
    /** 创建交易策略模块是否展开 */
    strategyMode: false,
    /** 「我不选择标的，我思考的是通用的交易体系」 */
    noSymbolMode: false,
    /** 策略模块规则勾选：入场规则/止损止盈/仓位管理 */
    strategyRules: { entry: false, stop: false, position: false } as Record<'entry' | 'stop' | 'position', boolean>,
    /** 功能卡片设定的 run_type（发送时带出；普通输入为 custom） */
    pendingRunType: null as QuickCardType | null,

    /* ---------- 流式 ---------- */
    streaming: false,
    streamingContent: '',
    /** 深度模式多智能体步骤（4.8.2，ReAct 工具步骤） */
    streamingSteps: [] as AgentStep[],
    /** 深度模式 5 节点时间线（阶段六 6.1：agent_step 事件驱动，live 与完成后回看共用） */
    timeline: [] as TimelineNode[],
    /** 策略模式输出结束后的按钮信息（4.5） */
    strategyOutput: null as StrategyOutputInfo | null,
    /** 策略生成校验通过信息（阶段八 7.3/7.5：strategy_ready 事件） */
    strategyReady: null as { strategyId: number; autoBacktest: boolean } | null,
    /** 策略生成后自动回测状态（阶段八 7.5） */
    autoBacktestStatus: 'idle' as 'idle' | 'running' | 'success' | 'failed',
    autoBacktestTaskId: null as number | null,
    autoBacktestResult: null as BacktestResult | null,
    autoBacktestError: null as string | null,

    /* ---------- 流式（阶段四增强：稳定性与错误体验） ---------- */
    /** 已收到的最后 delta seq（断点续传断点） */
    lastSeq: 0,
    /** 流式连接状态（idle/streaming/reconnecting/manual） */
    streamStatus: 'idle' as StreamStatus,
    /** 当前流式会话 id（断点续传用，done/error 事件可能更新） */
    streamConversationId: null as number | null,
    /** 错误帧信息（error 事件后按 code 分级展示） */
    streamError: null as { code?: string; message?: string; retryable?: boolean; retry_after?: number } | null,
    /** RATE_LIMITED 剩余倒计时（秒），>0 时禁用发送 */
    retryCountdown: 0,
    /** done(truncated=true) 是否发生（分析超时，已返回部分结果） */
    truncatedNotice: false,
    /** 降级模式标记：PROVIDER_UNAVAILABLE 时蓝色横幅 */
    degradedBanner: false,
    /** memory_saved 轻量提示（2s 自动消失） */
    memorySavedNotice: null as { summary: string; importance: number } | null,
    /** 最近一次发送载荷（NETWORK_ERROR 重试用） */
    lastPayload: null as StreamChatPayload | null,
    /** 断线自动重连已尝试次数（超过 3 次转手动） */
    reconnectAttempt: 0,
    /** 会话 token 累计用量（阶段八 7.1：usage 事件累计，切换会话重置） */
    tokenUsage: { prompt: 0, completion: 0, total: 0 } as { prompt: number; completion: number; total: number },
  }),
  actions: {
    /* ---------- 会话 ---------- */
    async loadConversations() {
      this.conversations = await fetchConversations()
    },
    async createConversation() {
      const conv = await apiCreateConversation()
      this.conversations.unshift(conv)
      this.activeConversationId = conv.id
      this.messages = []
      this.timeline = []
      this.tokenUsage = { prompt: 0, completion: 0, total: 0 }
      return conv
    },
    async openConversation(id: number) {
      this.activeConversationId = id
      this.messages = await fetchMessages(id)
      this.timeline = []
      this.tokenUsage = { prompt: 0, completion: 0, total: 0 }
    },
    removeConversation(id: number) {
      this.conversations = this.conversations.filter((c) => c.id !== id)
      if (this.activeConversationId === id) {
        this.activeConversationId = null
        this.messages = []
      }
    },

    /* ---------- 策略 ---------- */
    async loadStrategies() {
      this.strategies = await fetchStrategies()
    },
    /** 打开策略 N 区（点击 M/J 策略行） */
    async openStrategy(id: number) {
      this.activeStrategy = await fetchStrategy(id)
      this.mode = 'strategy'
    },
    closeStrategy() {
      this.activeStrategy = null
      this.mode = 'chat'
    },
    /** 切换聊天/策略 tab 时重置右侧为默认页面（K+L区：空会话+欢迎页+功能卡片） */
    resetPanel() {
      this.abortStream()
      this.mode = 'chat'
      this.activeStrategy = null
      this.messages = []
      this.activeConversationId = null
      this.streamingContent = ''
      this.streamingSteps = []
      this.timeline = []
      this.strategyOutput = null
      this.tokenUsage = { prompt: 0, completion: 0, total: 0 }
    },

    /* ---------- Agent ---------- */
    async loadAgents() {
      this.agents = await fetchAgents()
    },

    /* ---------- 输入区 ---------- */
    setInputText(text: string) {
      this.inputText = text
    },
    selectSymbol(symbol: SymbolInfo | null) {
      this.selectedSymbol = symbol
    },
    /** 应用功能卡片：写 prompt + 设 run_type */
    applyCard(card: QuickCardType) {
      this.pendingRunType = card
    },
    resetCard() {
      this.pendingRunType = null
    },
    toggleRule(key: 'entry' | 'stop' | 'position') {
      this.strategyRules[key] = !this.strategyRules[key]
    },

    /* ---------- 流式 ---------- */
    startStreaming() {
      this.streaming = true
      this.streamingContent = ''
      this.streamingSteps = []
      // 注意：strategyOutput 在 send 时已由调用方 set（先于 streamSend），此处不再清空，
      // 否则会清掉本次策略输出的按钮信息（bug：setStrategyOutput 在 streamSend 之前）。
      this.strategyReady = null
      this.autoBacktestStatus = 'idle'
      this.autoBacktestTaskId = null
      this.autoBacktestResult = null
      this.autoBacktestError = null
      this.timeline = AGENT_NODE_ORDER.map((node) => ({ node, status: 'waiting' as const }))
    },
    appendStreamContent(text: string, node?: string) {
      this.streamingContent += text
      if (node) {
        // 阶段六：深度模式节点内容改由 timeline 累积，此处不再写 streamingSteps
        const tl = this.timeline.find((n) => n.node === node)
        if (tl) tl.content = (tl.content ?? '') + text
      }
    },
    pushToolStep(step: AgentStep) {
      this.streamingSteps.push(step)
    },
    endStreaming() {
      this.streaming = false
    },
    /** 策略模式结束：记录按钮信息 */
    setStrategyOutput(info: StrategyOutputInfo) {
      this.strategyOutput = info
    },
    clearStrategyOutput() {
      this.strategyOutput = null
    },

    /* ---------- 流式编排（阶段四：断点续传/重连/错误处理） ---------- */

    /**
     * 发起流式对话（含断线自动续传）：
     * POST /chat 主流 → 网络中断自动 GET /chat/resume 补发（指数退避，>3 次转手动）
     * → resync 全量重载 / done(truncated) 部分结果 / error 分级降级。
     */
    async streamSend(payload: StreamChatPayload) {
      const token = ++streamToken
      if (streamAbort) {
        streamAbort.abort()
        streamAbort = null
      }
      this.startStreaming()
      this.streamStatus = 'streaming'
      this.streamConversationId = payload.conversation_id ?? null
      this.lastSeq = 0
      this.reconnectAttempt = 0
      this.streamError = null
      this.truncatedNotice = false
      this.degradedBanner = false
      this.lastPayload = payload

      streamAbort = new AbortController()
      await streamChat(
        payload,
        {
          onEvent: (ev) => this._handleSSEEvent(ev),
          onDone: async () => {
            if (token !== streamToken) return
            await this._finalizeStream()
          },
          onError: (err) => {
            if (token !== streamToken) return
            void this._handleStreamError(err)
          },
        },
        streamAbort.signal
      )
    },

    /** SSE 事件分发：按类型更新流式内容 / 步骤 / 错误 / 记忆反馈 */
    _handleSSEEvent(ev: SSEEvent) {
      switch (ev.type) {
        case 'delta':
          if (typeof ev.seq === 'number') this.lastSeq = ev.seq
          if (ev.content) this.appendStreamContent(ev.content, ev.node)
          break
        case 'tool_call':
          this.pushToolStep({
            step_name: `tool:${ev.tool ?? '?'}`,
            content: JSON.stringify(ev.input ?? {}),
            agent_role: 'assistant',
          })
          break
        case 'tool_result':
          this.pushToolStep({ step_name: `tool_result:${ev.tool ?? '?'}`, content: ev.preview ?? '', agent_role: 'tool' })
          break
        case 'done':
          if (ev.conversation_id) {
            this.activeConversationId = ev.conversation_id
            this.streamConversationId = ev.conversation_id
          }
          if (ev.truncated) this.truncatedNotice = true
          break
        case 'error':
          this.streamError = {
            code: ev.code,
            message: ev.message,
            retryable: ev.retryable,
            retry_after: ev.retry_after,
          }
          if (ev.conversation_id) this.streamConversationId = ev.conversation_id
          if (ev.code === 'RATE_LIMITED') this.startRetryCountdown(ev.retry_after ?? 30)
          break
        case 'memory_saved':
          this.setMemorySaved({ summary: ev.summary ?? '', importance: ev.importance ?? 5 })
          break
        case 'agent_step': {
          if (!ev.node) break
          const tl = this.timeline.find((n) => n.node === ev.node)
          if (!tl) break
          if (ev.status === 'running') {
            tl.status = 'running'
          } else {
            tl.status = ev.status === 'failed' ? 'failed' : 'done'
            if (ev.summary) tl.summary = ev.summary
            if (typeof ev.duration_ms === 'number') tl.duration_ms = ev.duration_ms
            if (ev.error) tl.error = ev.error
          }
          break
        }
        case 'usage': {
          // 阶段八 7.1：单轮 usage 事件（prompt/completion/total）累计到会话级
          this.tokenUsage.prompt += ev.prompt ?? 0
          this.tokenUsage.completion += ev.completion ?? 0
          this.tokenUsage.total += ev.total ?? 0
          break
        }
        case 'title': {
          // 阶段八 7.2：会话标题自动生成完成后更新 J 区列表，无需刷新
          if (ev.title && ev.conversation_id) {
            const conv = this.conversations.find((c) => c.id === ev.conversation_id)
            if (conv) conv.title = ev.title
          }
          break
        }
        case 'strategy_ready': {
          // 阶段八 7.3/7.5：策略校验通过并已保存，刷新 M 区；有标的则自动发起回测
          const strategyId = ev.strategy_id ?? 0
          this.strategyReady = { strategyId, autoBacktest: !!ev.auto_backtest }
          void this.loadStrategies()
          if (ev.auto_backtest && strategyId && this.strategyOutput?.symbolId) {
            void this.runAutoBacktest(strategyId, this.strategyOutput.symbolId)
          }
          break
        }
        default:
          break
      }
    },

    /** 主流错误处理：HTTP/服务端错误收尾；网络中断尝试断点续传 */
    async _handleStreamError(err: Error) {
      if (err.name === 'AbortError') return
      const terminal = err.message.includes('请求失败') || err.message.includes('无响应')
      if (terminal) {
        this.streamError = { code: 'NETWORK_ERROR', message: err.message, retryable: true }
        await this._finalizeStream()
        return
      }
      await this._resumeLoop(streamToken)
    },

    /** 断线自动续传：指数退避（1s/2s/4s，上限 30s），>3 次转手动 */
    async _resumeLoop(token: number) {
      if (token !== streamToken) return
      if (!this.streamConversationId) {
        await this._finalizeStream()
        return
      }
      if (this.reconnectAttempt >= 3) {
        this.streamStatus = 'manual'
        return
      }
      this.streamStatus = 'reconnecting'
      const delay = Math.min(1000 * 2 ** this.reconnectAttempt, 30000)
      this.reconnectAttempt++
      await sleep(delay)
      if (token !== streamToken) return
      const outcome = await this._doResumeOnce(token)
      if (outcome === 'done' || outcome === 'resync') return
      await this._resumeLoop(token)
    },

    /** 执行一次断点续传（GET /chat/resume），返回 done/resync/failed */
    async _doResumeOnce(token: number): Promise<'done' | 'resync' | 'failed'> {
      const convId = this.streamConversationId
      if (!convId) return 'failed'
      streamAbort = new AbortController()
      let resyncSeen = false
      let doneSeen = false
      let errored = false
      await resumeChat(
        convId,
        this.lastSeq,
        {
          onEvent: (ev) => {
            if (ev.type === 'resync') {
              resyncSeen = true
              return
            }
            this._handleSSEEvent(ev)
          },
          onDone: () => {
            doneSeen = true
          },
          onError: (err) => {
            if (err.name !== 'AbortError') errored = true
          },
        },
        streamAbort.signal
      )
      if (token !== streamToken) return 'done'
      if (resyncSeen) {
        await this._reloadConversation()
        return 'resync'
      }
      if (doneSeen || !errored) {
        await this._finalizeStream()
        return 'done'
      }
      return 'failed'
    },

    /** 用户点击「连接中断，点击继续」后手动续传 */
    async resumeManual() {
      if (this.streamStatus !== 'manual') return
      this.streamStatus = 'streaming'
      this.reconnectAttempt = 0
      await this._resumeLoop(streamToken)
    },

    /** NETWORK_ERROR 重发：重新发送最近一次载荷 */
    async retrySend() {
      if (!this.lastPayload || this.streaming) return
      await this.streamSend(this.lastPayload)
    },

    /** 策略生成后自动回测（阶段八 7.5）：POST /backtest → 2s 轮询任务 → 成功后取结果 */
    async runAutoBacktest(strategyId: number, symbolId: number) {
      this.autoBacktestStatus = 'running'
      this.autoBacktestTaskId = null
      this.autoBacktestResult = null
      this.autoBacktestError = null
      try {
        const task = await createBacktest({ strategy_id: strategyId, symbol: symbolId, period: '1d' })
        this.autoBacktestTaskId = task.id
        for (;;) {
          await sleep(2000)
          const t = await fetchBacktestTask(task.id)
          if (t.status === 'success') {
            const results = await fetchBacktestResults(strategyId)
            this.autoBacktestResult = results[0] ?? null
            this.autoBacktestStatus = 'success'
            break
          }
          if (t.status === 'failed') {
            this.autoBacktestStatus = 'failed'
            this.autoBacktestError = t.error || '回测失败'
            break
          }
        }
      } catch (e) {
        this.autoBacktestStatus = 'failed'
        this.autoBacktestError = (e as Error).message || '回测失败'
      }
    },

    /** 中止当前流（切换会话/重置面板/卸载时） */
    abortStream() {
      streamToken++
      if (streamAbort) {
        streamAbort.abort()
        streamAbort = null
      }
      if (retryTimer) {
        clearInterval(retryTimer)
        retryTimer = null
      }
      this.streaming = false
      this.streamStatus = 'idle'
      this.streamError = null
      this.retryCountdown = 0
      this.timeline = []
    },

    /** 流结束收尾：把流式增量落为正式消息；降级模式拉取后端已入库内容 */
    async _finalizeStream() {
      const convId = this.streamConversationId ?? this.activeConversationId
      const code = this.streamError?.code
      if (code === 'PROVIDER_UNAVAILABLE') {
        // 降级模式：后端把基础分析文案入库但 error 帧不带内容，重新拉取展示
        this.degradedBanner = true
        if (convId) await this._reloadLastAssistantMessage(convId)
        this.endStreaming()
        return
      }
      if (this.streamError) {
        // 其它错误：不展示流式增量，由 UI 按错误类型分级提示
        this.streamingContent = ''
        this.streamingSteps = []
        this.timeline = []
        this.endStreaming()
        return
      }
      if (this.streamingContent) {
        this.messages.push({
          id: Date.now(),
          conversation_id: convId ?? 0,
          role: 'assistant',
          content: this.streamingContent,
          created_at: new Date().toISOString(),
        })
      }
      this.endStreaming()
      void this.loadConversations()
    },

    /** 拉取会话最后一条 assistant 消息（降级内容展示，避免与流式内容重复） */
    async _reloadLastAssistantMessage(convId: number) {
      try {
        const msgs = await fetchMessages(convId)
        const lastAssistant = [...msgs].reverse().find((m) => m.role === 'assistant')
        if (lastAssistant) {
          const last = this.messages[this.messages.length - 1]
          if (!last || !(last.role === 'assistant' && last.id === lastAssistant.id)) {
            this.messages.push(lastAssistant)
          }
        }
      } catch {
        /* 拉取失败不阻断，UI 已显示降级横幅 */
      }
    },

    /** resync：断点续传缓存已过期，全量重载该会话消息 */
    async _reloadConversation() {
      const convId = this.streamConversationId
      this.streamingContent = ''
      this.streamingSteps = []
      if (convId) {
        this.activeConversationId = convId
        try {
          this.messages = await fetchMessages(convId)
        } catch {
          /* 重载失败保留已有流式内容，正常收尾 */
        }
      }
      this.endStreaming()
      this.streamStatus = 'idle'
      void this.loadConversations()
    },

    /** RATE_LIMITED 倒计时：期间发送按钮禁用 */
    startRetryCountdown(seconds: number) {
      this.retryCountdown = Math.max(1, seconds)
      if (retryTimer) clearInterval(retryTimer)
      retryTimer = window.setInterval(() => {
        if (this.retryCountdown <= 1) {
          this.retryCountdown = 0
          this.streamError = null
          if (retryTimer) {
            clearInterval(retryTimer)
            retryTimer = null
          }
        } else {
          this.retryCountdown--
        }
      }, 1000)
    },

    /** memory_saved 轻量提示：2s 自动消失，不打断对话 */
    setMemorySaved(notice: { summary: string; importance: number }) {
      this.memorySavedNotice = notice
      if (memoryTimer) clearTimeout(memoryTimer)
      memoryTimer = window.setTimeout(() => {
        this.memorySavedNotice = null
      }, 2000)
    },
  },
})
