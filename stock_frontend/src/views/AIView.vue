<script setup lang="ts">
// 阶段四实现：J 会话侧边栏 / K 标题区 / L 功能卡片与输入区 / M 策略与记忆 / N 策略显示
</script>

<template>
  <div class="ai-placeholder">
    <div class="ph-card">
      <h2>AI 策略页</h2>
      <p class="ph-desc">J 会话侧边栏 / K 标题区 / L 功能卡片与输入区 / M 策略与记忆 / N 策略显示</p>
      <p class="ph-note">该区域将在阶段四开发完成，布局高仿 QuantDinger。</p>
    </div>
  </div>
</template>

<style scoped>
.ai-placeholder {
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
