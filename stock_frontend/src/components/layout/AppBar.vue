<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useThemeStore } from '@/stores/theme'
import { toast } from '@/utils/toast'
import BaseButton from '@/components/base/BaseButton.vue'

const router = useRouter()
const user = useUserStore()
const theme = useThemeStore()

function onLogout() {
  user.logout()
  toast.info('已退出登录')
  router.push({ name: 'login' })
}
</script>

<template>
  <header class="appbar">
    <div class="appbar__brand">
      <span class="appbar__logo">K</span>
      <span class="appbar__name">量化交易终端</span>
    </div>

    <nav class="appbar__nav">
      <RouterLink to="/market" class="appbar__link">行情</RouterLink>
      <RouterLink to="/ai" class="appbar__link">AI 策略</RouterLink>
    </nav>

    <div class="appbar__right">
      <button
        class="icon-btn"
        :title="theme.mode === 'dark' ? '切换到明亮模式' : '切换到暗黑模式'"
        @click="theme.toggle()"
      >
        {{ theme.mode === 'dark' ? '☀' : '🌙' }}
      </button>

      <div class="user-chip" :title="user.displayName">
        <span class="user-chip__avatar">{{ user.avatarText }}</span>
        <span class="user-chip__name">{{ user.displayName || '未登录' }}</span>
      </div>

      <BaseButton variant="ghost" size="sm" @click="onLogout">退出</BaseButton>
    </div>
  </header>
</template>

<style scoped>
.appbar {
  display: flex;
  align-items: center;
  gap: 24px;
  flex: none;
  height: 44px;
  padding: 0 16px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
}
.appbar__brand {
  display: flex;
  align-items: center;
  gap: 8px;
}
.appbar__logo {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 5px;
  background: var(--accent);
  color: #fff;
  font-size: 14px;
  font-weight: 700;
}
.appbar__name {
  font-size: 14px;
  font-weight: 600;
}
.appbar__nav {
  display: flex;
  gap: 4px;
}
.appbar__link {
  padding: 5px 12px;
  border-radius: 4px;
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.appbar__link:hover {
  color: var(--text);
  background: var(--bg-hover);
}
.appbar__link.router-link-active {
  color: var(--text);
  background: var(--bg-active);
}
.appbar__right {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-left: auto;
}
.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  font-size: 15px;
  color: var(--text-secondary);
}
.icon-btn:hover {
  background: var(--bg-hover);
  color: var(--text);
}
.user-chip {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 10px 3px 3px;
  border-radius: 16px;
  background: var(--bg-hover);
}
.user-chip__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.user-chip__name {
  font-size: 12px;
  color: var(--text-secondary);
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
