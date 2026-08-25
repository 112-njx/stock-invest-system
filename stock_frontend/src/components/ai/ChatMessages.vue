<script setup lang="ts">
/**
 * 对话消息流：
 * - 历史消息（ai.messages）+ 流式增量（打字机效果，markdown 渲染）
 * - 深度模式：回复下方「查看分析过程」折叠面板（4.8.3）
 * - 创建交易策略模式：输出结束下方「保存交易策略 / 回测显示」（4.5）
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAiStore } from '@/stores/ai'
import { updateStrategy } from '@/api/ai'
import { renderMarkdown } from '@/utils/markdown'
import { toast } from '@/utils/toast'
import MessageBubble from '@/components/ai/MessageBubble.vue'
import AgentStepsPanel from '@/components/ai/AgentStepsPanel.vue'
import AgentTimeline from '@/components/ai/AgentTimeline.vue'

const ai = useAiStore()
const router = useRouter()
const scrollEl = ref<HTMLElement | null>(null)

/** 深度分析时间线是否可见（任一节点已非等待态，即收到过 agent_step 事件） */
const showTimeline = computed(() => ai.timeline.some((n) => n.status !== 'waiting'))

/** 降级模式内容检测：后端降级文案统一以「AI服务暂时不可用」开头 */
function isDegradedContent(text?: string): boolean {
  return !!text && text.startsWith('AI服务暂时不可用')
}

/** 错误分级提示文案（阶段四 4.3） */
function errorNotice(ev: { code?: string; message?: string }) {
  switch (ev.code) {
    case 'TOKEN_INVALID':
    case 'TOKEN_QUOTA':
      return { text: 'API Key无效或余额不足，请检查配置', kind: 'danger' }
    case 'CONTENT_FILTERED':
      return { text: '内容涉及敏感话题，无法生成', kind: 'muted' }
    case 'PROVIDER_UNAVAILABLE':
      return { text: 'AI服务暂不可用，已切换基础分析模式', kind: 'degraded' }
    case 'NETWORK_ERROR':
      return { text: ev.message || '网络错误', kind: 'danger' }
    default:
      return { text: ev.message || 'AI 服务异常，请稍后重试', kind: 'danger' }
  }
}

watch(
  () => [ai.messages.length, ai.streamingContent, ai.streamingSteps.length] as const,
  async () => {
    await nextTick()
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  }
)

/** 保存策略（7.3）：策略已由后端生成校验并落库（draft），此处确认保存为 active */
async function onSaveStrategy() {
  if (!ai.strategyReady) return
  try {
    await updateStrategy(ai.strategyReady.strategyId, { status: 'active' })
    toast.success('交易策略已保存')
    void ai.loadStrategies()
  } catch {
    /* 错误已 toast */
  }
}

/** 查看详情（7.5）：跳转行情详情页 D 区策略指标（携带标的代码）；无标的则打开 N 区 */
function onViewDetail() {
  if (!ai.strategyReady) return
  const code = ai.strategyOutput?.symbolCode
  if (code) {
    router.push({
      path: '/market/detail',
      query: { strategy_id: String(ai.strategyReady.strategyId), symbol: code },
    })
  } else {
    void ai.openStrategy(ai.strategyReady.strategyId)
  }
}

/** 百分比 / 数值格式化（7.5 回测结果卡片） */
function pct(v?: number | null): string {
  return v == null ? '--' : `${(v * 100).toFixed(2)}%`
}
function num(v?: number | null): string {
  return v == null ? '--' : v.toFixed(2)
}
</script>

<template>
  <div ref="scrollEl" class="chat-messages">
    <div v-if="!ai.messages.length && !ai.streaming" class="chat-messages__empty">
      <p>开始和你的交易 Agent 对话</p>
      <p class="chat-messages__hint">可点击上方功能卡片快速填充问题</p>
    </div>

    <MessageBubble v-for="m in ai.messages" :key="m.id" :message="m" />

    <!-- 深度分析时间线（6.1/6.2）：流式时在气泡上方，完成后保留在消息下方供回看 -->
    <AgentTimeline v-if="showTimeline" :nodes="ai.timeline" :running="ai.streaming" />

    <!-- 流式增量（打字机） -->
    <div v-if="ai.streaming" class="chat-msg chat-msg--assistant">
      <div class="chat-msg__avatar chat-msg__avatar--ai">AI</div>
      <div class="chat-msg__body">
        <!-- 降级模式蓝色横幅（4.4） -->
        <div v-if="ai.degradedBanner || isDegradedContent(ai.streamingContent)" class="sse-banner sse-banner--degraded">
          AI服务暂不可用，以下为基于技术指标的基础分析
        </div>
        <div class="md-body" v-html="renderMarkdown(ai.streamingContent)" />
        <span v-if="!ai.streamingContent" class="chat-msg__cursor">AI 思考中…</span>
        <AgentStepsPanel
          v-if="ai.streamingSteps.length"
          :steps="ai.streamingSteps"
          :running="ai.streaming"
        />
        <!-- 断线状态（4.1）：自动重连 / 手动续传 -->
        <div v-if="ai.streamStatus === 'reconnecting'" class="sse-status">
          连接中断，正在重连…
        </div>
        <div v-else-if="ai.streamStatus === 'manual'" class="sse-status sse-status--manual">
          <span>连接中断</span>
          <button class="sse-status__btn" @click="ai.resumeManual()">点击继续</button>
        </div>
      </div>
    </div>

    <!-- 流式结束后的状态提示（4.2/4.3）：超时部分结果 / 错误分级 / memory_saved 轻量反馈 -->
    <div v-if="!ai.streaming && ai.truncatedNotice" class="sse-notice sse-notice--muted">
      分析超时，已返回部分结果
    </div>
    <div
      v-if="
        !ai.streaming &&
        ai.streamError &&
        ai.streamError.code !== 'RATE_LIMITED' &&
        ai.streamError.code !== 'PROVIDER_UNAVAILABLE'
      "
      class="sse-error"
      :class="`sse-error--${errorNotice(ai.streamError).kind}`"
    >
      <span>{{ errorNotice(ai.streamError).text }}</span>
      <button v-if="ai.streamError.code === 'NETWORK_ERROR'" class="sse-status__btn" @click="ai.retrySend()">
        点击重试
      </button>
    </div>
    <div v-if="ai.memorySavedNotice" class="sse-memory">
      <span class="sse-memory__dot" />已记住：{{ ai.memorySavedNotice.summary }}
    </div>

    <!-- 策略生成校验状态（7.3）+ 自动回测结果内嵌（7.5） -->
    <div v-if="ai.strategyOutput" class="strategy-result">
      <!-- 生成中（流式期间） -->
      <div v-if="ai.streaming" class="sr-status">
        <span class="sr-status__loading">正在生成策略…</span>
      </div>

      <!-- 校验结果（流结束） -->
      <template v-else>
        <div v-if="ai.strategyReady" class="sr-status">
          <span class="sr-status__ok">✓ 校验通过</span>
          <button class="chat-msg__btn chat-msg__btn--primary" @click="onSaveStrategy">保存策略</button>
        </div>
        <div v-else class="sr-status">
          <span class="sr-status__fail">生成失败，请调整描述或使用模板</span>
        </div>

        <!-- 自动回测（7.5，有标的时） -->
        <div v-if="ai.strategyReady && ai.strategyOutput.hasSymbol" class="sr-backtest">
          <div v-if="ai.autoBacktestStatus === 'running'" class="sr-bt__progress">回测中…</div>
          <div v-else-if="ai.autoBacktestStatus === 'failed'" class="sr-bt__fail">
            回测失败{{ ai.autoBacktestError ? '：' + ai.autoBacktestError : '' }}
          </div>
          <div v-else-if="ai.autoBacktestStatus === 'success' && ai.autoBacktestResult" class="sr-bt__result">
            <div class="sr-bt__metrics">
              <div class="sr-metric">
                <span class="sr-metric__label">胜率</span>
                <span class="sr-metric__value">{{ pct(ai.autoBacktestResult.win_rate) }}</span>
              </div>
              <div class="sr-metric">
                <span class="sr-metric__label">盈亏比</span>
                <span class="sr-metric__value">{{ num(ai.autoBacktestResult.profit_loss_ratio) }}</span>
              </div>
              <div class="sr-metric">
                <span class="sr-metric__label">最大回撤</span>
                <span class="sr-metric__value">{{ pct(ai.autoBacktestResult.max_drawdown) }}</span>
              </div>
              <div class="sr-metric">
                <span class="sr-metric__label">年化收益</span>
                <span class="sr-metric__value">{{ pct(ai.autoBacktestResult.annual_return) }}</span>
              </div>
            </div>
            <button class="chat-msg__btn" @click="onViewDetail">查看详情</button>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.chat-messages {
  height: 100%;
  overflow-y: auto;
  padding: 10px 16px 4px;
}
.chat-messages__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 6px;
  color: var(--text-muted);
  font-size: 13px;
}
.chat-messages__hint {
  font-size: 12px;
}
.chat-msg {
  display: flex;
  gap: 10px;
  padding: 8px 0;
}
.chat-msg__avatar {
  flex: none;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
}
.chat-msg__avatar--ai {
  background: var(--accent-soft);
  color: var(--accent);
}
.chat-msg__body {
  flex: 1;
  min-width: 0;
  max-width: 88%;
}
.chat-msg__cursor {
  font-size: 12px;
  color: var(--text-muted);
}
/* 阶段四：降级横幅 / 连接状态 / 错误提示 / memory_saved */
.sse-banner {
  margin-bottom: 6px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
}
.sse-banner--degraded {
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
  border-left: 2px solid var(--accent);
}
.sse-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.sse-status--manual {
  color: var(--text-secondary);
}
.sse-status__btn {
  flex: none;
  height: 26px;
  padding: 0 12px;
  border-radius: 4px;
  font-size: 12px;
  color: var(--accent);
  border: 1px solid var(--accent);
  background: transparent;
  transition: background-color 0.15s;
}
.sse-status__btn:hover {
  background: var(--accent-soft);
}
.sse-notice {
  padding: 4px 12px;
  font-size: 12px;
}
.sse-notice--muted {
  color: var(--text-muted);
}
.sse-error {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 6px 0 8px;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
}
.sse-error--danger {
  color: var(--up);
  background: var(--up-soft);
  border-left: 2px solid var(--up);
}
.sse-error--warn {
  color: var(--ind-dea);
  background: rgba(245, 158, 11, 0.1);
  border-left: 2px solid var(--ind-dea);
}
.sse-error--muted {
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border-left: 2px solid var(--border-strong);
}
.sse-error--degraded {
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
  border-left: 2px solid var(--accent);
}
.sse-memory {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 0 8px;
  padding: 4px 12px;
  font-size: 12px;
  color: var(--text-muted);
}
.sse-memory__dot {
  flex: none;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--down);
}
.strategy-result {
  margin: 8px 0;
  padding: 10px 12px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.sr-status {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
}
.sr-status__loading {
  color: var(--text-muted);
}
.sr-status__ok {
  color: var(--down);
  font-weight: 600;
}
.sr-status__fail {
  color: var(--up);
}
.sr-backtest {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed var(--border);
  font-size: 12px;
}
.sr-bt__progress {
  color: var(--accent);
}
.sr-bt__fail {
  color: var(--up);
}
.sr-bt__result {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sr-bt__metrics {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
}
.sr-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  background: var(--bg-panel);
  border-radius: 4px;
}
.sr-metric__label {
  font-size: 11px;
  color: var(--text-muted);
}
.sr-metric__value {
  font-size: 15px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.chat-msg__btn {
  height: 30px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  transition: background-color 0.15s, color 0.15s;
}
.chat-msg__btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.chat-msg__btn--primary {
  background: var(--accent);
  border-color: transparent;
  color: #fff;
}
.chat-msg__btn--primary:hover {
  filter: brightness(1.1);
}
</style>
