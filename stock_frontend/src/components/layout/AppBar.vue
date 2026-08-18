<script setup lang="ts">
/**
 * 顶部导航栏：品牌 + 路由 + 主题切换。
 * 优化1：删除顶部用户头像/用户名和退出按钮，统一收归行情页 I 区用户 Cell 下拉菜单。
 */
import { useThemeStore } from '@/stores/theme'

const theme = useThemeStore()
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
</style>
