<script setup lang="ts">
// 阶段二/三实现：A K线图 / B 技术指标 / C 基本数据 / D 重点关注列表
</script>

<template>
  <div class="detail-placeholder">
    <div class="ph-card">
      <h2>行情页 · 第一层</h2>
      <p class="ph-desc">A K 线图 / B 技术指标 / C 基本数据 / D 重点关注列表</p>
      <p class="ph-note">该区域将在阶段二开发完成，双击 K 线或 Esc 键可进出。</p>
    </div>
  </div>
</template>

<style scoped>
.detail-placeholder {
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
