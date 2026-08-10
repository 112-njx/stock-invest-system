<script setup lang="ts">
/**
 * J 区 · 会话侧边栏（4.1）：
 * - 顶部「策略/聊天」切换标识，当前页标识底部浅白色圆角背景
 * - 聊天页：历史会话列表 / 新建会话 / 点击加载消息 / 行内删除
 * - 策略页：交易策略列表（点击 → 右侧切 N 区）
 */
import { ref } from 'vue'
import { useAiStore } from '@/stores/ai'
import { deleteConversation } from '@/api/ai'

type JTab = 'chat' | 'strategy'

const ai = useAiStore()
const tab = ref<JTab>('chat')

function onNewConversation() {
  void ai.createConversation()
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
    <div class="j-tabs">
      <button class="j-tab" :class="{ active: tab === 'chat' }" @click="tab = 'chat'">聊天</button>
      <button class="j-tab" :class="{ active: tab === 'strategy' }" @click="tab = 'strategy'">策略</button>
    </div>

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
        <div v-if="!ai.conversations.length" class="j-empty">暂无会话，点击下方新建</div>
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

    <div class="j-new">
      <button v-if="tab === 'chat'" class="j-new__btn" @click="onNewConversation">＋ 新建会话</button>
      <button v-else class="j-new__btn" @click="tab = 'chat'">← 返回聊天</button>
    </div>
  </div>
</template>

<style scoped>
.j-sidebar {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.j-tabs {
  flex: none;
  display: flex;
  gap: 4px;
  padding: 10px 10px 6px;
}
.j-tab {
  flex: 1;
  height: 30px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  transition:
    background-color 0.15s,
    color 0.15s;
}
.j-tab:hover {
  color: var(--text);
}
/* 当前页标识底部浅白色圆角背景 */
.j-tab.active {
  background: rgba(255, 255, 255, 0.12);
  color: var(--text);
  font-weight: 500;
}
[data-theme='light'] .j-tab.active {
  background: rgba(0, 0, 0, 0.08);
}
.j-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 6px 8px;
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
.j-new {
  flex: none;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
}
.j-new__btn {
  width: 100%;
  height: 30px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  background: var(--bg-panel-2);
  border: 1px solid var(--border-strong);
  transition: background-color 0.15s, color 0.15s;
}
.j-new__btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
</style>
