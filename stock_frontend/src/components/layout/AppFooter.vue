<script setup lang="ts">
/**
 * G03：底部版权条（所有页面可见）。
 * 「© 2026 stock-agent-聂久翔 | 免责声明 | 隐私政策」
 */
</script>

<template>
  <footer class="app-footer">
    <span class="app-footer__copy">© 2026 stock-agent-聂久翔</span>
    <span class="app-footer__sep">|</span>
    <RouterLink to="/disclaimer" class="app-footer__link">免责声明</RouterLink>
    <span class="app-footer__sep">|</span>
    <RouterLink to="/privacy" class="app-footer__link">隐私政策</RouterLink>
  </footer>
</template>

<style scoped>
.app-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex: none;
  height: 26px;
  padding: 0 12px;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-muted);
}
.app-footer__link {
  color: var(--text-muted);
  cursor: pointer;
}
.app-footer__link:hover {
  color: var(--accent);
  text-decoration: underline;
}
.app-footer__sep {
  color: var(--border-strong);
}
</style>
