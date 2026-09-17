<script setup lang="ts">
/**
 * G16：顶部系统公告 banner（可关闭）。
 * 展示活跃公告（未过期 + 未停用），用户关闭后按 id 记入 localStorage 不再打扰。
 */
import { computed } from 'vue'
import { useNotificationStore } from '@/stores/notification'

const store = useNotificationStore()

const current = computed(() => store.visibleAnnouncements[0] || null)

function onClose() {
  if (current.value) store.dismissAnnouncement(current.value.id)
}
</script>

<template>
  <div v-if="current" class="ann-banner" :class="`is-${current.type}`">
    <span class="ann-banner__tag">
      {{ current.type === 'maintenance' ? '维护' : current.type === 'warning' ? '重要' : '公告' }}
    </span>
    <span class="ann-banner__title">{{ current.title }}</span>
    <span class="ann-banner__content">{{ current.content }}</span>
    <button class="ann-banner__close" title="关闭" @click="onClose">✕</button>
  </div>
</template>

<style scoped>
.ann-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: none;
  padding: 6px 12px;
  font-size: 12px;
  background: var(--bg-panel-2);
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
}
.ann-banner.is-warning {
  background: rgba(245, 158, 11, 0.12);
  border-bottom-color: rgba(245, 158, 11, 0.35);
  color: #f59e0b;
}
.ann-banner.is-maintenance {
  background: rgba(239, 68, 68, 0.12);
  border-bottom-color: rgba(239, 68, 68, 0.35);
  color: #ef4444;
}
.ann-banner__tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid currentColor;
  font-size: 10px;
  font-weight: 600;
}
.ann-banner__title {
  flex: none;
  font-weight: 600;
  color: var(--text);
}
.ann-banner__content {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ann-banner__close {
  flex: none;
  width: 18px;
  height: 18px;
  border-radius: 3px;
  font-size: 11px;
  color: var(--text-muted);
  cursor: pointer;
}
.ann-banner__close:hover {
  background: var(--bg-hover);
  color: var(--text);
}
</style>
