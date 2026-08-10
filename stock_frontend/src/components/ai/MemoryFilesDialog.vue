<script setup lang="ts">
/**
 * 4.6 · 记忆文件弹窗：只读展示用户本地记忆文件列表。
 * 后端 GET /api/v1/memory/files 尚待实现（编排缺失，见 fixed.md），
 * 请求失败时展示占位说明，接口就绪后自动生效。
 */
import { onMounted, ref } from 'vue'
import { fetchMemoryFiles, type MemoryFileItem } from '@/api/ai'

const emit = defineEmits<{ (e: 'close'): void }>()

const files = ref<MemoryFileItem[]>([])
const loading = ref(true)
/** 后端接口是否可用（404/失败则占位） */
const available = ref(true)

onMounted(async () => {
  try {
    files.value = await fetchMemoryFiles()
  } catch {
    available.value = false
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="dialog-mask" @click.self="emit('close')">
    <div class="dialog">
      <header class="dialog__head">
        <h3 class="dialog__title">记忆文件</h3>
        <button class="dialog__close" @click="emit('close')">×</button>
      </header>

      <div class="dialog__body">
        <div v-if="loading" class="dlg-empty">加载中…</div>
        <div v-else-if="!available" class="dlg-empty">
          <p>记忆文件接口（GET /api/v1/memory/files）后端尚未实现，暂无可展示内容。</p>
          <p class="dlg-empty__hint">Agent 记忆将本地存储于用户目录 data/memory/{user_id}/*.md，待后端补齐后此处自动展示。</p>
        </div>
        <div v-else-if="!files.length" class="dlg-empty">暂无记忆文件</div>
        <div v-else class="memory-list">
          <div v-for="(f, i) in files" :key="i" class="memory-item">
            <div class="memory-item__head">
              <span class="memory-item__path">{{ f.path }}</span>
              <span class="memory-item__type">{{ f.content_type || 'rule' }}</span>
            </div>
            <pre v-if="f.content" class="memory-item__content">{{ f.content }}</pre>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dialog-mask {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
}
.dialog {
  width: 520px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: var(--shadow);
  overflow: hidden;
}
.dialog__head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.dialog__title {
  font-size: 15px;
  font-weight: 600;
}
.dialog__close {
  width: 26px;
  height: 26px;
  font-size: 18px;
  color: var(--text-muted);
  border-radius: 4px;
}
.dialog__close:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.dialog__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 12px 16px;
}
.dlg-empty {
  padding: 28px 12px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.dlg-empty__hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
}
.memory-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.memory-item {
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.memory-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--bg-panel-2);
}
.memory-item__path {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  font-family: monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.memory-item__type {
  flex: none;
  font-size: 11px;
  color: var(--accent);
  background: var(--accent-soft);
  border-radius: 3px;
  padding: 0 6px;
}
.memory-item__content {
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  padding: 8px 10px;
  max-height: 160px;
  overflow-y: auto;
  font-family: inherit;
}
</style>
