<script setup lang="ts">
// 阶段二实现：E 重点关注列 / F 单击K线 / G 大盘指数 / H 行业指数 / I 通用设置
</script>

<template>
  <div class="market-placeholder">
    <div class="ph-card">
      <h2>行情页 · 第二层</h2>
      <p class="ph-desc">E 重点关注股票列 / F 单击 K 线图 / G 大盘指数 / H 行业指数 / I 通用设置</p>
      <p class="ph-note">该区域将在阶段二开发完成，当前为占位页。</p>
    </div>
  </div>
</template>

<style scoped>
.market-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  height: 100%;
  background: var(--bg);
}
.ph-card {
  text-align: center;
  padding: 40px 60px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.ph-card h2 {
  font-size: 18px;
  margin-bottom: 10px;
}
.ph-desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.ph-note {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
