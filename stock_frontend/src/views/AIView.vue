<script setup lang="ts">
/**
 * AI 策略页（阶段四）· J/K/L/M/N 区，高仿 QuantDinger 分区架构：
 * - J 会话侧边栏（策略/聊天切换）
 * - K 顶部标题介绍 / L 功能卡片 + 输入区（默认）
 * - M 交易策略 + 记忆文件 + 我的 Agent + 运行记录
 * - N 交易策略显示区（点击 M/J 策略后替换 K+L）
 */
import { onMounted, onUnmounted } from 'vue'
import { useAiStore, type QuickCardType } from '@/stores/ai'
import { useMarketStore } from '@/stores/market'
import SessionSidebar from '@/components/ai/SessionSidebar.vue'
import WelcomeHeader from '@/components/ai/WelcomeHeader.vue'
import ChatMessages from '@/components/ai/ChatMessages.vue'
import QuickCards from '@/components/ai/QuickCards.vue'
import ChatInput from '@/components/ai/ChatInput.vue'
import StrategyDetailPanel from '@/components/ai/StrategyDetailPanel.vue'

const ai = useAiStore()
const market = useMarketStore()

/** 功能卡片 → run_type（发送时映射，create 对应后端 strategy） */
const CARD_RUN_TYPE: Record<QuickCardType, string> = {
  create: 'strategy',
  diagnose: 'diagnose',
  plan: 'plan',
  radar: 'radar',
}

/** 功能卡片 prompt 模板（docs.md 4.1 诊断 / 4.2 交易计划 / 4.3 机会雷达） */
function cardPrompt(card: Exclude<QuickCardType, 'create'>, name: string): string {
  if (card === 'diagnose') {
    return `请使用系统行情数据，为「${name}」生成一份可执行的交易分析。

要求：
1. 说明当前价格、K 线周期和数据时间；如果数据不可用，请明确说明，不要编造。
2. 分析趋势、成交量、关键支撑/阻力、资金流和风险。
3. 给出偏多、震荡和偏空三种触发条件。
4. 提供具体行动：观察价位、入场确认、失效止损，以及止盈/减仓逻辑。
5. 结论优先，不要只返回通用框架。`
  }
  if (card === 'plan') {
    return `请为「${name}」制定一份可执行的交易计划：方向判断、关键价位、入场触发、止损、止盈、仓位控制，以及什么情况下应该等待不做。`
  }
  return `请基于当前选中的「${name}」分析标的做机会雷达扫描。
要求：
1. 分析必须锁定当前标的和市场。
2. 找出未来24小时可能触发的交易机会。
3. 列出触发条件、确认信号、失效位和主要风险。
4. 区分事实、假设和不确定性。
5. 输出要简洁，可执行。`
}

/** 策略模块规则文案（docs.md：入场/止损/仓位） */
const RULE_TEXTS: Record<'entry' | 'stop' | 'position', string> = {
  entry: '使用清晰的入场条件，并避免在行情末端追涨杀跌。',
  stop: '加入稳健的止损和止盈规则。',
  position: '加入简单的仓位管理，并限制每笔交易的最大风险。',
}

function buildRuleText(): string {
  return (Object.keys(RULE_TEXTS) as Array<'entry' | 'stop' | 'position'>)
    .filter((k) => ai.strategyRules[k])
    .map((k) => RULE_TEXTS[k])
    .join('\n')
}

/** 功能卡片点击：写 prompt / 展开策略模块 */
function onCardClick(card: QuickCardType) {
  ai.pendingRunType = card
  if (card === 'create') {
    ai.strategyMode = true
    ai.setInputText('请帮我创建一个交易策略，我会补充入场想法。')
    return
  }
  // 点击其余三个卡片时自动收起策略模块（bug4-1）
  ai.strategyMode = false
  ai.noSymbolMode = false
  ai.strategyRules = { entry: false, stop: false, position: false }
  const name = ai.selectedSymbol ? `${ai.selectedSymbol.name}（${ai.selectedSymbol.type}）` : '当前标的'
  ai.setInputText(cardPrompt(card, name))
}

/** 发送：SSE 流式对话（深度模式走 LangGraph，步骤经 delta+node 透传；断线续传/错误处理在 store 编排） */
async function send() {
  const content = ai.inputText.trim()
  if (!content || ai.streaming) return
  if (!ai.activeConversationId) await ai.createConversation()

  const finalContent = ai.strategyMode ? `${content}\n${buildRuleText()}`.trim() : content
  const symbol = ai.noSymbolMode ? null : ai.selectedSymbol
  const runType = ai.pendingRunType ? CARD_RUN_TYPE[ai.pendingRunType] : ai.deepMode ? 'diagnose' : 'custom'

  // 本地先行回显用户消息
  ai.messages.push({
    id: -Date.now(),
    conversation_id: ai.activeConversationId ?? 0,
    role: 'user',
    content: finalContent,
    created_at: new Date().toISOString(),
  })
  ai.setInputText('')
  if (runType === 'strategy') {
    ai.setStrategyOutput({
      conversationId: ai.activeConversationId ?? 0,
      description: finalContent,
      hasSymbol: !!symbol,
    })
  }

  await ai.streamSend({
    content: finalContent,
    conversation_id: ai.activeConversationId,
    symbol: symbol ? symbol.id : null,
    agent_id: ai.selectedAgentId || null,
    run_type: runType,
  })
}

onMounted(() => {
  void ai.loadConversations()
  void ai.loadStrategies()
  void ai.loadAgents()
  // 双向标的联动：从行情页进入 AI 页时，若 AI 页尚未选择标的则默认带出当前行情页标的
  if (!ai.selectedSymbol && market.current) {
    ai.selectSymbol(market.current)
  }
})

// 离开 AI 页时中止流式连接，避免后台残留请求
onUnmounted(() => {
  ai.abortStream()
})
</script>

<template>
  <div class="ai-shell">
    <!-- 左侧固定侧边栏：J（tabs+菜单）+ M（列表区），优化5 合并到 SessionSidebar -->
    <aside class="ai-side">
      <SessionSidebar />
    </aside>

    <!-- 右侧主区：K+L（默认）与 N 区互斥切换 -->
    <main class="ai-main">
      <StrategyDetailPanel v-if="ai.mode === 'strategy'" @back="ai.closeStrategy()" />
      <div v-else class="ai-main__chat">
        <!-- K 区标题 + L 区功能卡片：仅在无消息（新会话/未发送）时显示，发送后隐藏避免遮挡聊天（bug4-2） -->
        <WelcomeHeader v-if="!ai.messages.length && !ai.streaming" />
        <ChatMessages class="ai-main__scroll" />
        <QuickCards v-if="!ai.messages.length && !ai.streaming" @select="onCardClick" />
        <ChatInput @send="send" />
      </div>
    </main>
  </div>
</template>

<style scoped>
.ai-shell {
  display: flex;
  flex: 1;
  min-height: 0;
  background: var(--bg);
}
.ai-side {
  flex: none;
  width: 250px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-panel);
}
.ai-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ai-main__chat {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.ai-main__scroll {
  flex: 1;
  min-height: 0;
}
</style>
