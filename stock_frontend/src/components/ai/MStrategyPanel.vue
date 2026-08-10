<script setup lang="ts">
/**
 * M 区 · 交易策略 + 记忆文件 + 我的 Agent + 运行记录：
 * - 交易策略列表（行样式同会话），点击某策略 → 右侧 K+L 切换为 N 区
 * - 「记忆文件」→ 只读展示本地记忆文件
 * - 「我的 Agent」→ 创建/配置/启停
 * - 「运行记录」→ Agent 多智能体运行历史（4.8.4）
 */
import { ref } from 'vue'
import { useAiStore } from '@/stores/ai'
import MemoryFilesDialog from '@/components/ai/MemoryFilesDialog.vue'
import AgentManageDialog from '@/components/ai/AgentManageDialog.vue'
import AgentRunsDialog from '@/components/ai/AgentRunsDialog.vue'

const ai = useAiStore()
const showMemory = ref(false)
const showAgents = ref(false)
const showRuns = ref(false)
</script>

<template>
  <div class="m-panel">
    <header class="m-panel__head">
      <span class="m-panel__title">交易策略与记忆</span>
      <span class="m-panel__count">{{ ai.strategies.length }}</span>
    </header>

    <div class="m-panel__list">
      <div v-if="!ai.strategies.length" class="m-empty">暂无策略，创建交易策略后保存</div>
      <div
        v-for="s in ai.strategies"
        :key="s.id"
        class="m-item"
        :class="{ active: ai.mode === 'strategy' && ai.activeStrategy?.id === s.id }"
        @click="ai.openStrategy(s.id)"
      >
        <span class="m-item__title">{{ s.title }}</span>
        <span class="m-item__time">{{ (s.created_at || '').slice(5, 10) }}</span>
      </div>
    </div>

    <div class="m-panel__ops">
      <button class="m-op" @click="showMemory = true">记忆文件</button>
      <button class="m-op" @click="showAgents = true">我的 Agent</button>
      <button class="m-op" @click="showRuns = true">运行记录</button>
    </div>

    <MemoryFilesDialog v-if="showMemory" @close="showMemory = false" />
    <AgentManageDialog v-if="showAgents" @close="showAgents = false" />
    <AgentRunsDialog v-if="showRuns" @close="showRuns = false" />
  </div>
</template>

<style scoped>
.m-panel {
  flex: none;
  display: flex;
  flex-direction: column;
  max-height: 42%;
  min-height: 0;
  border-top: 1px solid var(--border);
}
.m-panel__head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
}
.m-panel__title {
  font-size: 12px;
  color: var(--text-secondary);
}
.m-panel__count {
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-panel-2);
  border-radius: 8px;
  padding: 0 6px;
}
.m-panel__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 6px;
}
.m-empty {
  padding: 14px 10px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
.m-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: background-color 0.15s;
}
.m-item:hover {
  background: var(--bg-hover);
}
.m-item.active {
  background: var(--bg-active);
  color: var(--text);
}
.m-item__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.m-item__time {
  flex: none;
  font-size: 11px;
  color: var(--text-muted);
}
.m-panel__ops {
  flex: none;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
}
.m-op {
  height: 26px;
  border-radius: 5px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  transition: background-color 0.15s, color 0.15s;
}
.m-op:hover {
  background: var(--bg-hover);
  color: var(--text);
}
</style>
