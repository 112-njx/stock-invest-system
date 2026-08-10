<script setup lang="ts">
/**
 * L 区 · 输入区（4.3）+ 创建交易策略模块（4.4）：
 * ① 标的选择行：文字提示 + 可搜索下拉（名称 + 类型）
 * ② Agent 选择 + 深度分析开关（4.8.1）
 * ③ 创建交易策略模块（三层布局 + 规则按钮 + 「我不选择标的」）
 * ④ 大文本输入框（Enter 发送 / Shift+Enter 换行）
 * ⑤ 底部操作栏：左侧风险提示 + 右侧「发送」
 */
import { useAiStore } from '@/stores/ai'
import SymbolPicker from './SymbolPicker.vue'

const ai = useAiStore()
const emit = defineEmits<{ (e: 'send'): void }>()

function onSend() {
  if (!ai.inputText.trim() || ai.streaming) return
  emit('send')
}

function closeStrategyModule() {
  ai.strategyMode = false
  ai.noSymbolMode = false
  ai.resetCard()
}
</script>

<template>
  <div class="chat-input">
    <!-- ① 标的选择行 -->
    <div class="ci-row">
      <span class="ci-row__label">选择要分析的标的</span>
      <SymbolPicker v-model="ai.selectedSymbol" />
    </div>

    <!-- ② Agent 选择 + 深度分析 -->
    <div class="ci-row ci-row--meta">
      <span class="ci-row__label">使用哪个 Agent</span>
      <select class="ci-select" v-model="ai.selectedAgentId">
        <option :value="0">系统 Agent</option>
        <option v-for="a in ai.agents" :key="a.id" :value="a.id">{{ a.name }}</option>
      </select>
      <button
        class="ci-deep"
        :class="{ 'is-on': ai.deepMode }"
        :title="'深度分析：开启后普通提问也走多智能体（技术分析→多空辩论→风控→决策）'"
        @click="ai.deepMode = !ai.deepMode"
      >
        <span class="ci-deep__dot" />深度分析
      </button>
    </div>

    <!-- ③ 创建交易策略模块（4.4） -->
    <div v-if="ai.strategyMode" class="sm">
      <div class="sm__top">
        <span class="sm__icon">▦</span>
        <span class="sm__title">你希望策略怎么交易？</span>
        <span class="sm__tag">可直接发送</span>
        <button class="sm__close" title="关闭策略模块" @click="closeStrategyModule">×</button>
      </div>
      <div class="sm__mid">不需要写代码。可以直接发送，也可以点选你最关心的规则。</div>
      <div class="sm__rules">
        <button
          class="sm__rule"
          :class="{ 'is-on': ai.strategyRules.entry }"
          @click="ai.toggleRule('entry')"
        >
          + 入场规则
        </button>
        <button
          class="sm__rule"
          :class="{ 'is-on': ai.strategyRules.stop }"
          @click="ai.toggleRule('stop')"
        >
          + 止损止盈
        </button>
        <button
          class="sm__rule"
          :class="{ 'is-on': ai.strategyRules.position }"
          @click="ai.toggleRule('position')"
        >
          + 仓位管理
        </button>
      </div>
      <label class="sm__nosymbol">
        <input type="checkbox" v-model="ai.noSymbolMode" />
        <span>我不选择标的，我思考的是通用的交易体系</span>
      </label>
    </div>

    <!-- ④ 大文本输入框 -->
    <textarea
      v-model="ai.inputText"
      class="ci-textarea"
      rows="3"
      placeholder="例如：帮我分析一小时内上证指数的趋势……"
      @keydown.enter.exact.prevent="onSend"
    />

    <!-- ⑤ 底部操作栏 -->
    <div class="ci-bottom">
      <span class="ci-risk">风险提示：AI 输出仅用于研究参考，不构成投资建议。决策前请自行核对数据、风险和仓位。</span>
      <button
        class="ci-send"
        :class="{ 'is-disabled': !ai.inputText.trim() || ai.streaming }"
        :disabled="!ai.inputText.trim() || ai.streaming"
        @click="onSend"
      >
        发送
      </button>
    </div>
  </div>
</template>

<style scoped>
.chat-input {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 16px 12px;
  border-top: 1px solid var(--border);
}
.ci-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ci-row--meta {
  gap: 8px;
}
.ci-row__label {
  flex: none;
  font-size: 12px;
  color: var(--text-secondary);
}
.ci-select {
  height: 32px;
  padding: 0 8px;
  background: var(--bg-panel-2);
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}
.ci-select:focus {
  border-color: var(--accent);
}
.ci-deep {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
  height: 28px;
  padding: 0 10px;
  border-radius: 14px;
  font-size: 12px;
  color: var(--text-muted);
  border: 1px solid var(--border-strong);
  transition: all 0.15s;
}
.ci-deep__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
}
.ci-deep.is-on {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
.ci-deep.is-on .ci-deep__dot {
  background: var(--accent);
}
/* 创建交易策略模块 */
.sm {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.sm__top {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sm__icon {
  color: var(--accent);
  font-size: 14px;
}
.sm__title {
  font-size: 13px;
  font-weight: 600;
}
.sm__tag {
  margin-left: auto;
  font-size: 11px;
  color: var(--accent);
  background: var(--accent-soft);
  padding: 2px 8px;
  border-radius: 10px;
}
.sm__close {
  flex: none;
  width: 22px;
  height: 22px;
  font-size: 16px;
  line-height: 1;
  color: var(--text-muted);
  border-radius: 4px;
}
.sm__close:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.sm__mid {
  font-size: 12px;
  color: var(--text-muted);
}
.sm__rules {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.sm__rule {
  height: 28px;
  padding: 0 12px;
  border-radius: 14px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  transition: all 0.15s;
}
.sm__rule:hover {
  border-color: var(--accent);
  color: var(--text);
}
.sm__rule.is-on {
  color: var(--accent);
  border-color: var(--accent);
  background: var(--accent-soft);
}
.sm__nosymbol {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}
.sm__nosymbol input {
  accent-color: var(--accent);
}
.ci-textarea {
  width: 100%;
  resize: none;
  padding: 10px 12px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.ci-textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-soft);
}
.ci-textarea::placeholder {
  color: var(--text-muted);
}
.ci-bottom {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ci-risk {
  flex: 1;
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.5;
}
.ci-send {
  flex: none;
  height: 32px;
  padding: 0 22px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  background: var(--accent);
  transition: filter 0.15s, opacity 0.15s;
}
.ci-send:hover:not(.is-disabled) {
  filter: brightness(1.1);
}
.ci-send.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
