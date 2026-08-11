<script setup lang="ts">
/**
 * 对话消息流：
 * - 历史消息（ai.messages）+ 流式增量（打字机效果，markdown 渲染）
 * - 深度模式：回复下方「查看分析过程」折叠面板（4.8.3）
 * - 创建交易策略模式：输出结束下方「保存交易策略 / 回测显示」（4.5）
 */
import { nextTick, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAiStore } from '@/stores/ai'
import { createStrategy, generateStrategy } from '@/api/ai'
import { renderMarkdown } from '@/utils/markdown'
import { toast } from '@/utils/toast'
import MessageBubble from '@/components/ai/MessageBubble.vue'
import AgentStepsPanel from '@/components/ai/AgentStepsPanel.vue'

const ai = useAiStore()
const router = useRouter()
const scrollEl = ref<HTMLElement | null>(null)
/** 本次策略输出已保存的 strategy_id（未保存时回测先自动保存） */
const savedStrategyId = ref<number | null>(null)

watch(
  () => [ai.messages.length, ai.streamingContent, ai.streamingSteps.length] as const,
  async () => {
    await nextTick()
    if (scrollEl.value) scrollEl.value.scrollTop = scrollEl.value.scrollHeight
  }
)

/** 确保策略已保存：AI 生成代码/参数（容错）→ 入库 → 返回 id */
async function ensureSaved(): Promise<number> {
  if (savedStrategyId.value) return savedStrategyId.value
  const description = ai.strategyOutput?.description || ai.streamingContent || 'AI 生成策略'
  const title = description.split('\n')[0].slice(0, 24) || 'AI 生成策略'
  let code: string | undefined
  let params: Record<string, unknown> | undefined
  try {
    const gen = await generateStrategy(description, ai.selectedSymbol?.id)
    code = gen.code || undefined
    params = gen.params || undefined
  } catch {
    /* 生成失败仅保存描述，N 区代码留空 */
  }
  const s = await createStrategy({ title, description, code, params, status: 'active' })
  savedStrategyId.value = s.id
  void ai.loadStrategies()
  return s.id
}

async function onSaveStrategy() {
  try {
    const id = await ensureSaved()
    toast.success('交易策略已保存')
    // 未选择标的：文案为「保存该交易策略到回测页面」，保存后跳转 N 区便于回测
    if (ai.strategyOutput && !ai.strategyOutput.hasSymbol) {
      await ai.openStrategy(id)
    }
  } catch {
    /* 错误已 toast */
  }
}

async function onBacktest() {
  try {
    const id = await ensureSaved()
    // 双向标的联动：携带发送时选中的标的代码，行情第一层据此切换 K 线标的
    const sym = ai.selectedSymbol
    router.push({
      path: '/market/detail',
      query: {
        strategy_id: String(id),
        ...(sym ? { symbol: sym.code } : {}),
      },
    })
  } catch {
    /* 错误已 toast */
  }
}
</script>

<template>
  <div ref="scrollEl" class="chat-messages">
    <div v-if="!ai.messages.length && !ai.streaming" class="chat-messages__empty">
      <p>开始和你的交易 Agent 对话</p>
      <p class="chat-messages__hint">可点击上方功能卡片快速填充问题</p>
    </div>

    <MessageBubble v-for="m in ai.messages" :key="m.id" :message="m" />

    <!-- 流式增量（打字机） -->
    <div v-if="ai.streaming" class="chat-msg chat-msg--assistant">
      <div class="chat-msg__avatar chat-msg__avatar--ai">AI</div>
      <div class="chat-msg__body">
        <div class="md-body" v-html="renderMarkdown(ai.streamingContent)" />
        <span v-if="!ai.streamingContent" class="chat-msg__cursor">思考中…</span>
        <AgentStepsPanel
          v-if="ai.streamingSteps.length"
          :steps="ai.streamingSteps"
          :running="ai.streaming"
        />
      </div>
    </div>

    <!-- 策略模式输出结束后的操作栏（4.5）：保存交易策略 / 回测显示 -->
    <div v-if="!ai.streaming && ai.strategyOutput" class="strategy-actions">
      <span class="strategy-actions__tip">AI 已给出交易策略建议</span>
      <button class="chat-msg__btn chat-msg__btn--primary" @click="onSaveStrategy">
        {{ ai.strategyOutput.hasSymbol ? '保存交易策略' : '保存该交易策略到回测页面' }}
      </button>
      <button class="chat-msg__btn" @click="onBacktest">回测显示</button>
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
.strategy-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0 8px;
}
.strategy-actions__tip {
  font-size: 12px;
  color: var(--text-muted);
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
