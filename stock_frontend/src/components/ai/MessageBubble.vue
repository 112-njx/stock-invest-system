<script setup lang="ts">
/**
 * 对话消息气泡：用户（右侧）/ AI（左侧，markdown 渲染）。
 * 历史消息由后端 chat_messages 提供；流式增量由 ChatMessages 单独渲染。
 * 降级模式：AI 回复若为后端基础分析文案（4.4），气泡上方显示蓝色横幅。
 */
import type { ChatMessage } from '@/api/ai'
import { renderMarkdown } from '@/utils/markdown'

defineProps<{ message: ChatMessage }>()

/** 降级模式内容检测：后端降级文案统一以「AI服务暂时不可用」开头 */
function isDegradedContent(text?: string): boolean {
  return !!text && text.startsWith('AI服务暂时不可用')
}
</script>

<template>
  <div class="chat-msg" :class="`chat-msg--${message.role}`">
    <div v-if="message.role === 'assistant'" class="chat-msg__avatar chat-msg__avatar--ai">AI</div>
    <div class="chat-msg__body">
      <div
        v-if="message.role === 'assistant' && isDegradedContent(message.content)"
        class="msg-banner msg-banner--degraded"
      >
        AI服务暂不可用，以下为基于技术指标的基础分析
      </div>
      <div v-if="message.role === 'assistant'" class="md-body" v-html="renderMarkdown(message.content)" />
      <div v-else class="chat-msg__user">{{ message.content }}</div>
    </div>
    <div v-if="message.role === 'user'" class="chat-msg__avatar chat-msg__avatar--me">我</div>
  </div>
</template>

<style scoped>
.chat-msg {
  display: flex;
  gap: 10px;
  padding: 8px 0;
}
.chat-msg--user {
  justify-content: flex-end;
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
.chat-msg__avatar--me {
  background: var(--bg-hover);
  color: var(--text-secondary);
}
.chat-msg__body {
  flex: 1;
  min-width: 0;
  max-width: 82%;
}
/* 用户消息 row-reverse 下 body 不拉伸，气泡靠右（bug4-3） */
.chat-msg--user .chat-msg__body {
  flex: none;
}
.chat-msg__user {
  display: inline-block;
  padding: 9px 12px;
  border-radius: 8px;
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
/* 降级模式横幅（4.4） */
.msg-banner {
  margin-bottom: 6px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
}
.msg-banner--degraded {
  color: #93c5fd;
  background: rgba(59, 130, 246, 0.12);
  border-left: 2px solid var(--accent);
}
</style>
