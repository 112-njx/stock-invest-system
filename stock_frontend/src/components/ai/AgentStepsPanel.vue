<script setup lang="ts">
/**
 * 4.8.3 · 多智能体步骤展开面板（AI 回复气泡下方）：
 * 时间线展示各智能体节点输出（技术分析师/看多研究员/看空研究员/风控经理/交易决策），
 * 节点状态（运行中/完成），节点输出摘要可点击展开全文。
 */
import { reactive, ref } from 'vue'
import type { AgentStep } from '@/api/ai'

const props = defineProps<{ steps: AgentStep[]; running?: boolean }>()

const NODE_LABEL: Record<string, string> = {
  technical_analyst: '技术分析师',
  bull_researcher: '看多研究员',
  bear_researcher: '看空研究员',
  risk_manager: '风控经理',
  trader: '交易决策',
}

const open = ref(false)
const expanded = reactive<boolean[]>([])

function stepLabel(step: AgentStep): string {
  if (step.step_name.startsWith('tool_result:')) return '工具结果'
  if (step.step_name.startsWith('tool:')) return `工具：${step.step_name.slice(5)}`
  return NODE_LABEL[step.step_name] ?? step.step_name
}

function toggle(i: number) {
  expanded[i] = !expanded[i]
}
</script>

<template>
  <div class="steps-panel">
    <button class="steps-panel__toggle" @click="open = !open">
      <span>{{ open ? '收起' : '查看' }}分析过程（{{ steps.length }} 步）</span>
      <span class="steps-panel__arrow">{{ open ? '▲' : '▼' }}</span>
    </button>

    <div v-if="open" class="steps-panel__list">
      <div v-for="(s, i) in steps" :key="i" class="step">
        <div class="step__head" @click="toggle(i)">
          <span class="step__dot" :class="{ 'is-running': running && i === steps.length - 1 }" />
          <span class="step__name">{{ stepLabel(s) }}</span>
          <span class="step__status">{{ running && i === steps.length - 1 ? '运行中…' : '完成' }}</span>
          <span class="step__arrow">{{ expanded[i] ? '▾' : '▸' }}</span>
        </div>
        <pre v-if="expanded[i]" class="step__content">{{ s.content }}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.steps-panel {
  margin-top: 6px;
  border-top: 1px dashed var(--border);
  padding-top: 6px;
}
.steps-panel__toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.steps-panel__toggle:hover {
  color: var(--text-secondary);
}
.steps-panel__arrow {
  font-size: 10px;
}
.steps-panel__list {
  margin-top: 6px;
  border-left: 2px solid var(--border);
  padding-left: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.step__head {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 2px 0;
}
.step__head:hover {
  color: var(--text);
}
.step__dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--down);
}
.step__dot.is-running {
  background: var(--accent);
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}
.step__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.step__status {
  flex: none;
  font-size: 11px;
  color: var(--text-muted);
}
.step__arrow {
  flex: none;
  font-size: 10px;
  color: var(--text-muted);
}
.step__content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border-radius: 4px;
  padding: 8px;
  margin: 4px 0 2px;
  max-height: 200px;
  overflow-y: auto;
  font-family: inherit;
}
</style>
