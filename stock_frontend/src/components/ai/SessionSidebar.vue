<script setup lang="ts">
/**
 * J 区 + M 区 · 侧边栏（优化5 重构）：
 * - 顶部「聊天/策略」切换标识（带原生 SVG 图标，居中对齐）
 * - 垂直菜单（4 项，左对齐，图标+文字）：创建新会话/返回聊天、记忆文件、我的 Agent、运行记录
 * - 分隔符 + 分区标题：聊天模式「当前聊天记录」、策略模式「交易策略与记忆」
 * - 列表区：聊天会话 / 交易策略
 */
import { ref } from 'vue'
import { useAiStore } from '@/stores/ai'
import { deleteConversation } from '@/api/ai'
import MemoryFilesDialog from '@/components/ai/MemoryFilesDialog.vue'
import AgentManageDialog from '@/components/ai/AgentManageDialog.vue'
import AgentRunsDialog from '@/components/ai/AgentRunsDialog.vue'

type JTab = 'chat' | 'strategy'

const ai = useAiStore()
const tab = ref<JTab>('chat')

const showMemory = ref(false)
const showAgents = ref(false)
const showRuns = ref(false)

/** 切换聊天/策略 tab：右侧重置为默认页面（K+L区），不保持原来的聊天/策略内容 */
function switchTab(newTab: JTab) {
  if (tab.value === newTab) return
  tab.value = newTab
  ai.resetPanel()
}

function onNewOrBack() {
  if (tab.value === 'chat') {
    void ai.createConversation()
  } else {
    switchTab('chat')
  }
}

async function onDeleteConversation(id: number) {
  try {
    await deleteConversation(id)
    ai.removeConversation(id)
  } catch {
    /* 错误已 toast */
  }
}

function formatTime(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
</script>

<template>
  <div class="j-sidebar">
    <!-- 顶部 tabs：聊天 / 策略（图标+文字居中） -->
    <div class="j-tabs">
      <button class="j-tab" :class="{ active: tab === 'chat' }" @click="switchTab('chat')">
        <!-- 聊天：线性轮廓云图标 -->
        <svg class="j-tab__icon" viewBox="0 0 88 72" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round">
          <path d="M16 42 A20 20 0 0 1 40 20 A24 24 0 0 1 70 40 L70 60 L12 60 Z" />
        </svg>
        <span>聊天</span>
      </button>
      <button class="j-tab" :class="{ active: tab === 'strategy' }" @click="switchTab('strategy')">
        <!-- 策略：6 箭头汇聚圆心（实心） -->
        <svg class="j-tab__icon" viewBox="0 0 96 96" fill="currentColor">
          <path d="M48 12 L56 24 L40 24 Z M84 48 L72 56 L72 40 Z M48 84 L40 72 L56 72 Z M12 48 L24 40 L24 56 Z M70 26 L62 38 L74 44 Z M26 26 L34 38 L22 44 Z" />
        </svg>
        <span>策略</span>
      </button>
    </div>

    <!-- 垂直菜单：4 项（图标+间距+文字，左对齐） -->
    <div class="j-menu">
      <button class="j-menu__item" @click="onNewOrBack">
        <!-- 编辑/新建图标（策略模式下该选项为「返回聊天」，图标不变） -->
        <svg class="j-menu__icon" viewBox="0 0 88 88" fill="none" stroke="currentColor" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 20 A8 8 0 0 1 20 12 L68 12 A8 8 0 0 1 76 20 L76 32" />
          <path d="M76 56 L76 76 A8 8 0 0 1 68 84 L20 84 A8 8 0 0 1 12 76 L12 20" />
          <path d="M48 24 L72 48 M66 42 L42 66 L36 60 Z" />
        </svg>
        <span>{{ tab === 'chat' ? '创建新会话' : '返回聊天' }}</span>
      </button>

      <button class="j-menu__item" @click="showMemory = true">
        <!-- 记忆文件：空心轮廓云 -->
        <svg class="j-menu__icon" viewBox="0 0 88 72" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round">
          <path d="M16 42 A20 20 0 0 1 40 20 A24 24 0 0 1 70 40 L70 60 L12 60 Z" />
        </svg>
        <span>记忆文件</span>
      </button>

      <button class="j-menu__item" @click="showAgents = true">
        <!-- 我的 Agent：2x2 圆角方块网格 -->
        <svg class="j-menu__icon" viewBox="0 0 88 88" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round">
          <path d="M10 10 H34 V34 H10 Z M54 10 H78 V34 H54 Z M10 54 H34 V78 H10 Z M54 54 H78 V78 H54 Z" />
        </svg>
        <span>我的 Agent</span>
      </button>

      <button class="j-menu__item" @click="showRuns = true">
        <!-- 运行记录：双菱形叠加 -->
        <svg class="j-menu__icon" viewBox="0 0 88 88" fill="none" stroke="currentColor" stroke-width="4" stroke-linejoin="round">
          <path d="M44 8 L76 40 L44 72 L12 40 Z M44 32 L76 64 L44 88 L12 56 Z" />
        </svg>
        <span>运行记录</span>
      </button>
    </div>

    <!-- 分隔符 -->
    <div class="j-divider" />

    <!-- 分区标题 -->
    <div class="j-section-head">
      {{ tab === 'chat' ? '当前聊天记录' : '交易策略与记忆' }}
    </div>

    <!-- 列表区 -->
    <div class="j-list">
      <!-- 聊天页：历史会话 -->
      <template v-if="tab === 'chat'">
        <div
          v-for="c in ai.conversations"
          :key="c.id"
          class="j-item"
          :class="{ active: c.id === ai.activeConversationId }"
          @click="ai.openConversation(c.id)"
        >
          <span class="j-item__title">{{ c.title }}</span>
          <span class="j-item__time">{{ formatTime(c.updated_at) }}</span>
          <button class="j-item__del" title="删除会话" @click.stop="onDeleteConversation(c.id)">×</button>
        </div>
        <div v-if="!ai.conversations.length" class="j-empty">暂无会话，点击上方新建</div>
      </template>

      <!-- 策略页：交易策略列表 -->
      <template v-else>
        <div
          v-for="s in ai.strategies"
          :key="s.id"
          class="j-item"
          :class="{ active: ai.mode === 'strategy' && ai.activeStrategy?.id === s.id }"
          @click="ai.openStrategy(s.id)"
        >
          <span class="j-item__title">{{ s.title }}</span>
          <span class="j-item__time">{{ formatTime(s.updated_at || s.created_at) }}</span>
        </div>
        <div v-if="!ai.strategies.length" class="j-empty">暂无策略，可在「创建交易策略」后保存</div>
      </template>
    </div>

    <!-- 对话框（原 MStrategyPanel 功能） -->
    <MemoryFilesDialog v-if="showMemory" @close="showMemory = false" />
    <AgentManageDialog v-if="showAgents" @close="showAgents = false" />
    <AgentRunsDialog v-if="showRuns" @close="showRuns = false" />
  </div>
</template>

<style scoped>
.j-sidebar {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

/* 顶部 tabs */
.j-tabs {
  flex: none;
  display: flex;
  gap: 4px;
  padding: 10px 10px 6px;
}
.j-tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  transition:
    background-color 0.15s,
    color 0.15s;
}
.j-tab:hover {
  background: var(--bg-hover);
}
.j-tab.active {
  background: rgba(255, 255, 255, 0.12);
  font-weight: 500;
}
[data-theme='light'] .j-tab.active {
  background: rgba(0, 0, 0, 0.08);
}
.j-tab__icon {
  width: 16px;
  height: 16px;
  flex: none;
}

/* 垂直菜单（4 项） */
.j-menu {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 8px;
}
.j-menu__item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text);
  text-align: left;
  transition: background-color 0.15s, color 0.15s;
}
.j-menu__item:hover {
  background: var(--bg-hover);
}
.j-menu__icon {
  width: 17px;
  height: 17px;
  flex: none;
}

/* 分隔符 */
.j-divider {
  flex: none;
  height: 1px;
  margin: 6px 12px;
  background: var(--border);
}

/* 分区标题 */
.j-section-head {
  flex: none;
  padding: 4px 14px 6px;
  font-size: 11px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
}

/* 列表区 */
.j-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 0 6px 8px;
}
.j-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: background-color 0.15s;
}
.j-item:hover {
  background: var(--bg-hover);
}
.j-item.active {
  background: var(--bg-active);
  color: var(--text);
}
.j-item__title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.j-item__time {
  flex: none;
  font-size: 11px;
  color: var(--text-muted);
}
.j-item__del {
  flex: none;
  width: 18px;
  height: 18px;
  font-size: 14px;
  line-height: 1;
  color: var(--text-muted);
  border-radius: 3px;
  visibility: hidden;
}
.j-item:hover .j-item__del {
  visibility: visible;
}
.j-item__del:hover {
  color: var(--up);
  background: var(--up-soft);
}
.j-empty {
  padding: 24px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
