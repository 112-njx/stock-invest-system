<script setup lang="ts">
/**
 * G16：顶部导航栏通知铃铛（未读红点 + 计数）→ 通知列表下拉面板。
 * 仅新增本组件并挂入 AppBar 右侧区块，不改动 AppBar 现有布局结构。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/stores/notification'

const router = useRouter()
const store = useNotificationStore()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

onMounted(() => {
  document.addEventListener('click', onDocClick)
  store.refreshUnread().catch(() => {})
})
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
})

function onDocClick(e: MouseEvent) {
  if (open.value && rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

async function toggle() {
  open.value = !open.value
  if (open.value) await store.load()
}

const badgeText = computed(() => (store.unread > 99 ? '99+' : String(store.unread)))

const TYPE_LABEL: Record<string, string> = {
  system: '系统',
  backtest_complete: '回测',
  agent_complete: 'AI',
  security: '安全',
}

function typeLabel(type: string): string {
  return TYPE_LABEL[type] || '通知'
}

async function onItemClick(id: number) {
  await store.markRead(id)
}

async function onMarkAll() {
  await store.markAllRead()
}

function onViewAll() {
  open.value = false
  router.push({ name: 'market' })
}

/** 相对时间：1 分钟内「刚刚」，1 小时内「N 分钟前」，24 小时内「N 小时前」，否则本地日期 */
function timeText(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const diff = Date.now() - t
  if (diff < 60_000) return '刚刚'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  const d = new Date(t)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
</script>

<template>
  <div class="bell" ref="rootRef">
    <button class="icon-btn bell__btn" title="通知" @click.stop="toggle">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 2a3.5 3.5 0 0 0-3.5 3.5v2.2L3.3 10h9.4l-1.2-2.3V5.5A3.5 3.5 0 0 0 8 2z" />
        <path d="M6.5 12.2a1.5 1.5 0 0 0 3 0" />
      </svg>
      <span v-if="store.unread > 0" class="bell__badge">{{ badgeText }}</span>
    </button>

    <Teleport to="body">
      <div v-if="open" class="notif-panel" @click.stop>
        <div class="notif-panel__head">
          <span class="notif-panel__title">通知</span>
          <button v-if="store.unread > 0" class="notif-panel__action" @click="onMarkAll">全部已读</button>
        </div>

        <div v-if="store.loading" class="notif-panel__empty">加载中…</div>
        <div v-else-if="store.items.length === 0" class="notif-panel__empty">暂无通知</div>
        <ul v-else class="notif-panel__list">
          <li
            v-for="item in store.items"
            :key="item.id"
            class="notif-item"
            :class="{ 'is-unread': !item.is_read }"
            @click="onItemClick(item.id)"
          >
            <div class="notif-item__row">
              <span class="notif-item__tag">{{ typeLabel(item.type) }}</span>
              <span class="notif-item__title">{{ item.title }}</span>
            </div>
            <p v-if="item.content" class="notif-item__content">{{ item.content }}</p>
            <span class="notif-item__time">{{ timeText(item.created_at) }}</span>
          </li>
        </ul>

        <div class="notif-panel__foot">
          <button class="notif-panel__link" @click="onViewAll">查看全部</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.bell {
  position: relative;
}
/* 与 AppBar 的 .icon-btn 视觉一致（scoped 样式不穿透子组件，此处自带一份） */
.bell__btn {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  color: var(--text-secondary);
  cursor: pointer;
}
.bell__btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.bell__badge {
  position: absolute;
  top: -2px;
  right: -4px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--down, #ef4444);
  color: #fff;
  font-size: 10px;
  line-height: 15px;
  text-align: center;
  font-weight: 600;
}

.notif-panel {
  position: fixed;
  top: 48px;
  right: 12px;
  z-index: 1500;
  width: 320px;
  max-height: 420px;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
}
.notif-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
}
.notif-panel__title {
  font-size: 13px;
  font-weight: 600;
}
.notif-panel__action,
.notif-panel__link {
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
}
.notif-panel__action:hover,
.notif-panel__link:hover {
  text-decoration: underline;
}
.notif-panel__empty {
  padding: 28px 12px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
.notif-panel__list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  margin: 0;
  padding: 0;
  list-style: none;
}
.notif-item {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background-color 0.15s;
}
.notif-item:hover {
  background: var(--bg-hover);
}
.notif-item.is-unread {
  border-left: 2px solid var(--accent);
}
.notif-item__row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.notif-item__tag {
  flex: none;
  padding: 1px 5px;
  border-radius: 3px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  font-size: 10px;
  color: var(--text-secondary);
}
.notif-item__title {
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.notif-item__content {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notif-item__time {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
}
.notif-panel__foot {
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  text-align: center;
}
</style>
