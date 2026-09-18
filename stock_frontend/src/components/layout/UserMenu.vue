<script setup lang="ts">
/**
 * G35（方案 B）· 顶部导航栏头像区：
 * - 未登录：默认头像 + 「登录」文字 → 打开登录/注册弹窗（Modal，不跳转页面）
 * - 已登录：头像 + 昵称 → 下拉菜单（个人设置 / 我的数据 / 通知中心 / 退出登录）
 *
 * 与 G16 铃铛并存：本组件仅作为 AppBar 右侧区块的新增项，不改动既有布局结构。
 * 「个人设置」「我的数据」指向首页 I 区（SettingsPanel）的对应区块；
 * 「通知中心」复用铃铛的同一个面板（状态在 notification store）。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthModalStore } from '@/stores/authModal'
import { useNotificationStore } from '@/stores/notification'
import { useUserStore } from '@/stores/user'
import { toast } from '@/utils/toast'

const route = useRoute()
const router = useRouter()
const user = useUserStore()
const modal = useAuthModalStore()
const notification = useNotificationStore()

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const menuPos = ref({ top: 0, right: 0 })

onMounted(() => document.addEventListener('mousedown', onDocMouseDown))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocMouseDown))

function onDocMouseDown(e: MouseEvent) {
  if (open.value && rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

function toggle() {
  // 未登录：直接弹登录框，不走下拉
  if (!user.token) {
    modal.show('login')
    return
  }
  if (!open.value && rootRef.value) {
    const rect = rootRef.value.getBoundingClientRect()
    menuPos.value = { top: rect.bottom + 6, right: window.innerWidth - rect.right }
  }
  open.value = !open.value
}

/** 个人设置 / 我的数据：跳首页 I 区并滚动到对应区块 */
function goSettings(hash: string) {
  open.value = false
  if (route.name === 'market-home') {
    // 已在首页：同 hash 的 push 不触发 watch，直接滚动
    document.getElementById(hash)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    return
  }
  router.push({ path: '/', hash: `#${hash}` })
}

function openNotifications() {
  open.value = false
  void notification.togglePanel()
}

async function onLogout() {
  open.value = false
  await user.logout() // G19：调后端吊销会话 + 清 Cookie + 清本地状态
  toast.info('已退出登录')
}

const menuStyle = computed(() => ({
  top: `${menuPos.value.top}px`,
  right: `${menuPos.value.right}px`,
}))
</script>

<template>
  <div ref="rootRef" class="um">
    <button class="um__btn" :title="user.token ? '账户菜单' : '登录 / 注册'" @click="toggle">
      <span class="um__avatar" :class="{ 'um__avatar--guest': !user.token }">
        {{ user.token ? user.avatarText : '👤' }}
      </span>
      <span class="um__name">{{ user.token ? user.displayName : '登录' }}</span>
    </button>

    <Teleport to="body">
      <div v-if="open" class="um-menu" :style="menuStyle">
        <div class="um-menu__head">
          <span class="um-menu__avatar">{{ user.avatarText }}</span>
          <div class="um-menu__meta">
            <span class="um-menu__display">{{ user.displayName }}</span>
            <span class="um-menu__sub">{{ user.user?.email || '未绑定邮箱' }}</span>
          </div>
        </div>
        <button class="um-menu__item" @click="goSettings('settings')">
          <span>个人设置</span>
          <span class="um-menu__arrow">›</span>
        </button>
        <button class="um-menu__item" @click="goSettings('settings-data')">
          <span>我的数据</span>
          <span class="um-menu__arrow">›</span>
        </button>
        <button class="um-menu__item" @click="openNotifications">
          <span>通知中心</span>
          <span v-if="notification.unread" class="um-menu__badge">{{ notification.unread }}</span>
        </button>
        <div class="um-menu__sep" />
        <button class="um-menu__item um-menu__item--danger" @click="onLogout">
          <span>退出登录</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.um {
  display: flex;
  align-items: center;
}
.um__btn {
  display: flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 8px;
  border-radius: 6px;
  color: var(--text-secondary);
  transition: background-color 0.15s;
}
.um__btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.um__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: var(--accent);
}
.um__avatar--guest {
  background: var(--bg-active);
  color: var(--text-muted);
  font-size: 12px;
}
.um__name {
  font-size: 12px;
  max-width: 96px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 下拉菜单 */
.um-menu {
  position: fixed;
  z-index: 1200;
  min-width: 200px;
  padding: 6px;
  background: var(--bg-panel);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
}
.um-menu__head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 8px 10px;
}
.um-menu__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  font-size: 13px;
  font-weight: 600;
  color: #fff;
  background: var(--accent);
}
.um-menu__meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.um-menu__display {
  font-size: 13px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.um-menu__sub {
  font-size: 11px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.um-menu__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  text-align: left;
  transition: background-color 0.15s;
}
.um-menu__item:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.um-menu__item--danger:hover {
  color: var(--up);
  background: var(--up-soft);
}
.um-menu__arrow {
  color: var(--text-muted);
}
.um-menu__badge {
  flex: none;
  min-width: 16px;
  padding: 0 5px;
  border-radius: 8px;
  font-size: 10px;
  line-height: 16px;
  text-align: center;
  color: #fff;
  background: var(--up);
}
.um-menu__sep {
  height: 1px;
  margin: 4px 6px;
  background: var(--border);
}
</style>
