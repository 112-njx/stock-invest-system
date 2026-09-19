<script setup lang="ts">
/**
 * G16：顶部导航栏通知铃铛（未读红点 + 计数）。
 * G35：面板开关由本地 ref 提到 notification store，供头像下拉菜单「通知中心」复用。
 * 重构：原 320px 下拉小面板改为居中大型弹窗（暗色遮罩盖住主页），
 * 修复旧面板 Teleport 到 body 后不在 rootRef 内、mousedown 外部点击判定
 * 会在 click 触发前关闭面板，导致「全部已读 / 单条已读」点击失效的问题。
 * 关闭方式：ESC、点击遮罩、右上角 ×、右下角「关闭公告」。
 */
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'
import { useNotificationStore } from '@/stores/notification'
import { useUserStore } from '@/stores/user'

const store = useNotificationStore()
const user = useUserStore()

onMounted(() => {
  document.addEventListener('keydown', onKeydown)
  // G35：未登录不发鉴权请求（401 会触发 refresh 失败分支把访客弹去登录页）
  if (user.token) store.refreshUnread().catch(() => {})
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
})

// G35：登录后补拉未读数（登出时由 App.vue 的 token watch 调 notification.clear）
watch(
  () => user.token,
  (token) => {
    if (token) store.refreshUnread().catch(() => {})
  }
)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && store.panelOpen) store.closePanel()
}

async function toggle() {
  await store.togglePanel()
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

/** 完整本地时间 YYYY-MM-DD HH:mm（大弹窗展示完整信息） */
function timeText(iso: string): string {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return iso
  const d = new Date(t)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}
</script>

<template>
  <!-- G35：未登录不渲染铃铛（通知是账号维度数据，访客无可展示内容） -->
  <div v-if="user.token" class="bell">
    <button class="icon-btn bell__btn" title="通知" @click.stop="toggle">
      <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round">
        <path d="M8 2a3.5 3.5 0 0 0-3.5 3.5v2.2L3.3 10h9.4l-1.2-2.3V5.5A3.5 3.5 0 0 0 8 2z" />
        <path d="M6.5 12.2a1.5 1.5 0 0 0 3 0" />
      </svg>
      <span v-if="store.unread > 0" class="bell__badge">{{ badgeText }}</span>
    </button>

    <Teleport to="body">
      <div v-if="store.panelOpen" class="notif-mask" @click.self="store.closePanel()">
        <div class="notif-modal" role="dialog" aria-modal="true" aria-label="通知中心">
          <header class="notif-modal__head">
            <h2 class="notif-modal__title">通知中心</h2>
            <div class="notif-modal__head-actions">
              <button v-if="store.unread > 0" class="notif-modal__readall" @click="onMarkAll">
                全部已读
              </button>
              <button class="notif-modal__close" type="button" title="关闭（ESC）" @click="store.closePanel()">
                ×
              </button>
            </div>
          </header>

          <div class="notif-modal__body">
            <div v-if="store.loading" class="notif-modal__empty">加载中…</div>
            <div v-else-if="store.items.length === 0" class="notif-modal__empty">暂无通知</div>
            <ul v-else class="notif-list">
              <li
                v-for="item in store.items"
                :key="item.id"
                class="notif-entry"
                :class="{ 'is-unread': !item.is_read }"
                @click="onItemClick(item.id)"
              >
                <span class="notif-entry__dot" :class="{ 'is-unread': !item.is_read }" />
                <div class="notif-entry__main">
                  <div class="notif-entry__row">
                    <span class="notif-entry__tag">{{ typeLabel(item.type) }}</span>
                    <span class="notif-entry__title">{{ item.title }}</span>
                  </div>
                  <p v-if="item.content" class="notif-entry__content">{{ item.content }}</p>
                  <span class="notif-entry__time">{{ timeText(item.created_at) }}</span>
                </div>
              </li>
            </ul>
          </div>

          <footer class="notif-modal__foot">
            <button type="button" class="notif-modal__ok" @click="store.closePanel()">关闭公告</button>
          </footer>
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

/* 大型弹窗：暗色遮罩盖住主页 */
.notif-mask {
  position: fixed;
  inset: 0;
  z-index: 1500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 16px;
  background: rgba(0, 0, 0, 0.55);
}
.notif-modal {
  display: flex;
  flex-direction: column;
  width: 720px;
  max-width: 100%;
  max-height: calc(100vh - 96px);
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 12px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.45);
}
.notif-modal__head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 22px 14px;
  border-bottom: 1px solid var(--border);
}
.notif-modal__title {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
  color: var(--text);
}
.notif-modal__head-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.notif-modal__readall {
  padding: 0;
  font-size: 12.5px;
  color: var(--accent);
  cursor: pointer;
}
.notif-modal__readall:hover {
  text-decoration: underline;
}
.notif-modal__close {
  flex: none;
  width: 28px;
  height: 28px;
  font-size: 18px;
  line-height: 1;
  color: var(--text-muted);
  border-radius: 4px;
}
.notif-modal__close:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.notif-modal__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 22px;
}
.notif-modal__empty {
  padding: 48px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.notif-list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.notif-entry {
  display: flex;
  gap: 10px;
  padding: 14px 8px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background-color 0.15s;
}
.notif-entry:hover {
  background: var(--bg-hover);
}
.notif-entry:last-child {
  border-bottom: none;
}
.notif-entry__dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin-top: 7px;
  border-radius: 50%;
  background: var(--border-strong);
}
.notif-entry__dot.is-unread {
  background: var(--accent);
}
.notif-entry__main {
  flex: 1;
  min-width: 0;
}
.notif-entry__row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.notif-entry__tag {
  flex: none;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--bg-panel-2);
  border: 1px solid var(--border);
  font-size: 10px;
  color: var(--text-secondary);
}
.notif-entry__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.notif-entry.is-unread .notif-entry__title {
  color: var(--text);
}
.notif-entry__content {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}
.notif-entry__time {
  display: block;
  margin-top: 6px;
  font-size: 11.5px;
  color: var(--text-muted);
}
.notif-modal__foot {
  flex: none;
  display: flex;
  justify-content: flex-end;
  padding: 12px 22px;
  border-top: 1px solid var(--border);
}
.notif-modal__ok {
  padding: 7px 20px;
  font-size: 13px;
  color: #fff;
  background: var(--accent);
  border-radius: 6px;
  transition: opacity 0.15s;
}
.notif-modal__ok:hover {
  opacity: 0.9;
}
</style>
