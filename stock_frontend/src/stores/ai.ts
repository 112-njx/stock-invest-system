import { defineStore } from 'pinia'
import type { SymbolInfo } from '@/api/market'
import {
  fetchAgents,
  fetchConversations,
  fetchMessages,
  fetchStrategies,
  createConversation as apiCreateConversation,
  fetchStrategy,
  type AgentConfig,
  type AgentStep,
  type ChatMessage,
  type Conversation,
  type Strategy,
} from '@/api/ai'

/** 卡片类型：创建交易策略 / 诊断符号 / 交易计划 / 机会雷达 */
export type QuickCardType = 'create' | 'diagnose' | 'plan' | 'radar'
/** 对话区展示模式：chat=聊天(K+L)，strategy=N区策略详情 */
export type AiPanelMode = 'chat' | 'strategy'

/** AI 策略输出后的操作信息（4.5：保存交易策略 / 回测显示） */
export interface StrategyOutputInfo {
  conversationId: number
  /** 用户发送的原始描述（保存策略用） */
  description: string
  /** 是否选择标的（未选择时按钮文案为「保存该交易策略到回测页面」） */
  hasSymbol: boolean
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
    /** 深度模式多智能体步骤（4.8.2） */
    streamingSteps: [] as AgentStep[],
    /** 策略模式输出结束后的按钮信息（4.5） */
    strategyOutput: null as StrategyOutputInfo | null,
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
      return conv
    },
    async openConversation(id: number) {
      this.activeConversationId = id
      this.messages = await fetchMessages(id)
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
      this.mode = 'chat'
      this.activeStrategy = null
      this.messages = []
      this.activeConversationId = null
      this.streamingContent = ''
      this.streamingSteps = []
      this.strategyOutput = null
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
      this.strategyOutput = null
    },
    appendStreamContent(text: string, node?: string) {
      this.streamingContent += text
      if (node) {
        // 深度模式：同一节点增量追加，节点名变化时新起一步
        const last = this.streamingSteps[this.streamingSteps.length - 1]
        if (last && last.step_name === node) {
          last.content += text
        } else {
          this.streamingSteps.push({ step_name: node, content: text, agent_role: 'assistant' })
        }
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
  },
})
