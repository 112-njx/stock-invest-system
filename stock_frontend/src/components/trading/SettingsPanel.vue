<script setup lang="ts">
/**
 * I 区 · 通用设置与开发者信息（第二层市场页）：
 * - 上部：用户头像及名称（登录信息，刷新后懒加载 /users/me）
 * - 中间：显示风格设置（暗黑/明亮，默认暗黑，即时切换并持久化）
 * - 下方：开发者信息
 */
import { onMounted } from 'vue'
import { useThemeStore } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

const theme = useThemeStore()
const user = useUserStore()

onMounted(() => {
  // 硬刷新后 store 只剩 token，懒加载用户信息以显示头像/名称
  if (!user.user && user.token) user.fetchMe().catch(() => {})
})
</script>

<template>
  <div class="settings-panel">
    <div class="settings-user">
      <span class="settings-user__avatar">{{ user.avatarText }}</span>
      <div class="settings-user__meta">
        <span class="settings-user__name">{{ user.displayName || '未登录' }}</span>
        <span class="settings-user__hint">登录用户</span>
      </div>
    </div>

    <div class="settings-block">
      <span class="settings-block__label">显示风格</span>
      <div class="settings-theme" role="group" aria-label="显示风格">
        <button
          class="settings-theme__opt"
          :class="{ active: theme.mode === 'dark' }"
          @click="theme.setMode('dark')"
        >
          暗黑
        </button>
        <button
          class="settings-theme__opt"
          :class="{ active: theme.mode === 'light' }"
          @click="theme.setMode('light')"
        >
          明亮
        </button>
      </div>
    </div>

    <div class="settings-dev">
      <span class="settings-dev__text">本软件由 Xhope(发誓不做夜猫子)全程开发</span>
    </div>
  </div>
</template>

<style scoped>
.settings-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  height: 100%;
  min-height: 0;
  padding: 10px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}
.settings-user {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 4px 10px;
  border-bottom: 1px solid var(--border);
}
.settings-user__avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  font-size: 17px;
  font-weight: 600;
  flex: none;
}
.settings-user__meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.settings-user__name {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.settings-user__hint {
  font-size: 11px;
  color: var(--text-muted);
}
.settings-block {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 2px 4px;
}
.settings-block__label {
  font-size: 13px;
  color: var(--text-secondary);
  flex: none;
}
.settings-theme {
  display: flex;
  gap: 2px;
  background: var(--bg-panel-2);
  border-radius: 4px;
  padding: 2px;
}
.settings-theme__opt {
  padding: 3px 12px;
  font-size: 12px;
  color: var(--text-secondary);
  border-radius: 3px;
  transition:
    background-color 0.15s,
    color 0.15s;
}
.settings-theme__opt:hover {
  color: var(--text);
}
.settings-theme__opt.active {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}
.settings-dev {
  margin-top: auto;
  padding: 6px 4px 2px;
  border-top: 1px solid var(--border);
}
.settings-dev__text {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.6;
}
</style>
