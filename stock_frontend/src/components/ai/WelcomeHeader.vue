<script setup lang="ts">
/**
 * K 区 · 顶部标题介绍区（4.2）：
 * 中部居中：图标 + 主标题《定制你的交易Agent》+ 辅助小字。
 */
</script>

<template>
  <div class="welcome-header">
    <div class="welcome-header__icon">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M12 2 4 6v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6l-8-4z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
    </div>
    <h2 class="welcome-header__title">定制你的交易 Agent</h2>
    <p class="welcome-header__sub">询问市场情况，解释日志，定制策略，永久记忆</p>
  </div>
</template>

<style scoped>
.welcome-header {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 14px 16px 6px;
  text-align: center;
}
.welcome-header__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 10px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 20px;
}
.welcome-header__icon svg {
  width: 20px;
  height: 20px;
}
.welcome-header__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.welcome-header__sub {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
