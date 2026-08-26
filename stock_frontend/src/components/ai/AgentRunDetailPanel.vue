<script setup lang="ts">
/**
 * 阶段六 6.3 · 运行记录详情（N 区位置）：
 * 点击运行记录后跳转至此，展示该次运行的元信息（类型/结论/耗时/时间）+ 完整决策链
 * （复用 AgentTimeline，传入历史步骤而非 SSE 实时数据）。
 */
import { useAiStore } from '@/stores/ai'
import AgentTimeline from '@/components/ai/AgentTimeline.vue'

const emit = defineEmits<{ (e: 'back'): void }>()

const ai = useAiStore()

const RUN_TYPE_LABEL: Record<string, string> = {
  diagnose: '诊断符号',
  plan: '交易计划',
  radar: '机会雷达',
  strategy: '创建策略',
  custom: '对话',
}

function formatDuration(ms?: number | null): string {
  if (ms == null) return '--'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<template>
  <div class="rd">
    <header class="rd__topbar">
      <button class="rd__back" @click="emit('back')">← 返回</button>
      <h2 class="rd__title">运行记录详情</h2>
      <span class="rd__spacer" />
    </header>

    <div v-if="!ai.runDetail" class="rd__empty">加载中…</div>
    <div v-else class="rd__body">
      <!-- 元信息 -->
      <section class="rd__section">
        <div class="rd__meta">
          <span class="rd__type">{{ RUN_TYPE_LABEL[ai.runDetail.run.run_type ?? 'custom'] ?? ai.runDetail.run.run_type }}</span>
          <span v-if="ai.runDetail.run.final_decision" class="rd__decision">{{ ai.runDetail.run.final_decision }}</span>
        </div>
        <p class="rd__input">{{ ai.runDetail.run.input }}</p>
        <p class="rd__meta-line">
          <span>耗时 {{ formatDuration(ai.runDetail.run.total_duration) }}</span>
          <span class="rd__sep">·</span>
          <span>{{ formatTime(ai.runDetail.run.created_at) }}</span>
        </p>
      </section>

      <!-- 决策链 -->
      <section class="rd__section">
        <h3 class="rd__h3">决策链（{{ ai.runDetail.steps.length }} 节点）</h3>
        <AgentTimeline v-if="ai.runDetail.steps.length" :nodes="ai.runDetail.steps" />
        <p v-else class="rd__hint">该记录暂无节点步骤输出</p>
      </section>
    </div>
  </div>
</template>

<style scoped>
.rd {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.rd__topbar {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
}
.rd__back {
  font-size: 13px;
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid var(--border-strong);
}
.rd__back:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.rd__title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  text-align: center;
}
.rd__spacer {
  flex: none;
  width: 48px;
}
.rd__empty {
  padding: 40px;
  text-align: center;
  color: var(--text-muted);
}
.rd__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.rd__section {
  text-align: center;
}
.rd__meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}
.rd__type {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border-radius: 3px;
  padding: 2px 8px;
}
.rd__decision {
  font-size: 12px;
  color: var(--down);
  background: var(--down-soft);
  border-radius: 3px;
  padding: 2px 8px;
}
.rd__input {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  text-align: left;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.rd__meta-line {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.rd__sep {
  color: var(--text-muted);
}
.rd__h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 10px;
  color: var(--text);
}
.rd__hint {
  font-size: 12px;
  color: var(--text-muted);
  padding: 12px 0;
}
</style>
